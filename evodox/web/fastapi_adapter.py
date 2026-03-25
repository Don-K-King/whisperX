from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote
from uuid import uuid4

from evodox.auth.context import AuthzError, authorize_request
from evodox.jobs.complete_upload_service import (
    CompleteUploadInput,
    CompleteUploadValidationError,
    QueueSelectionPolicy,
    complete_upload,
)
from evodox.jobs.create_service import CreateJobInput, ValidationError, create_job
from evodox.jobs.get_job_status_service import JobStatusNotFoundError, get_job_status
from evodox.jobs.lifecycle_service import JobLifecycleError, cancel_job, delete_job, pause_job, resume_job
from evodox.jobs.progress import derive_progress
from evodox.jobs.transcript_service import (
    TranscriptConflictError,
    TranscriptValidationError,
    UpdateTranscriptInput,
    UpdateTranscriptSpeakerLabelsInput,
    get_transcript,
    update_transcript,
    update_transcript_speaker_labels,
)
from evodox.jobs.transcript_correction_service import (
    CorrectionSessionApplyInput,
    CorrectionSessionCommitInput,
    CorrectionSessionCreateInput,
    CorrectionSessionOptionsInput,
    TranscriptStatusUpdateInput,
    apply_correction_operations,
    commit_correction_session,
    create_correction_session,
    discard_correction_session,
    get_correction_session,
    get_transcript_status,
    redo_correction_session,
    set_correction_session_options,
    undo_correction_session,
    update_transcript_status,
)
from evodox.jobs.export_service import ExportRequestInput, ExportValidationError, queue_export
from evodox.jobs.transcription_settings_service import (
    TranscriptionSettingsValidationError,
    get_transcription_settings,
    update_transcription_settings,
)


@dataclass(frozen=True)
class FastAPIAdapterSettings:
    expected_issuer: str
    expected_audience: str


def map_create_job_response(response: Any) -> dict[str, Any]:
    return {
        "job_id": response.job_id,
        "tenant_id": response.tenant_id,
        "status": response.status,
        "upload": {
            "session_id": response.upload.session_id,
            "presigned_url": response.upload.presigned_url,
            "expires_at": response.upload.expires_at,
        },
    }


def map_complete_upload_response(response: Any) -> dict[str, Any]:
    return {
        "job_id": response.job_id,
        "status": response.status,
        "queue": response.queue,
    }


def map_job_status_response(response: Any) -> dict[str, Any]:
    return {
        "job_id": response.job_id,
        "status": response.status,
        "progress": response.progress,
        "retention_until": response.retention_until,
    }


def map_job_list_item(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status", "created"))
    progress = derive_progress(status=status, raw_progress=row.get("progress"))
    return {
        "job_id": row.get("job_id"),
        "filename": row.get("filename"),
        "status": status,
        "progress": max(0, min(100, int(progress))),
        "retention_months": row.get("retention_months"),
        "created_at": row.get("created_at"),
    }


def map_jobs_list_response(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"jobs": [map_job_list_item(row) for row in rows]}


def map_job_media_source_response(
    *,
    job_id: str,
    row: dict[str, Any],
    media_base_url: str | None,
    media_bucket: str | None,
) -> dict[str, Any] | None:
    base_url = str(media_base_url or "").strip()
    bucket = str(media_bucket or "").strip().strip("/")
    object_key = str(row.get("object_key") or "").strip().lstrip("/")
    if not base_url or not bucket or not object_key:
        return None
    object_path = quote(f"{bucket}/{object_key}", safe="/")
    return {
        "job_id": job_id,
        "filename": row.get("filename"),
        "content_type": row.get("content_type"),
        "object_key": object_key,
        "media_url": f"{base_url.rstrip('/')}/{object_path}",
    }


def map_transcript_response(response: Any) -> dict[str, Any]:
    raw_segments = list(getattr(response, "segments", []) or [])
    normalized_segments: list[dict[str, Any]] = []
    for index, segment in enumerate(raw_segments):
        if not isinstance(segment, dict):
            continue
        normalized = dict(segment)
        segment_id = str(normalized.get("segment_id", "")).strip()
        if len(segment_id) == 0:
            normalized["segment_id"] = f"seg_{index + 1:06d}"
        normalized_segments.append(normalized)
    return {
        "job_id": response.job_id,
        "version": response.version,
        "segments": normalized_segments,
        "speaker_labels": dict(getattr(response, "speaker_labels", {}) or {}),
        "review_status": str(getattr(response, "review_status", "in_review")),
        "is_final": bool(getattr(response, "is_final", False)),
        "final_set_by": getattr(response, "final_set_by", None),
        "final_set_at": getattr(response, "final_set_at", None),
        "status_updated_at": getattr(response, "status_updated_at", None),
    }


def map_transcript_update_response(response: Any) -> dict[str, Any]:
    return {"job_id": response.job_id, "version": response.version, "saved_at": response.saved_at}


def map_correction_session_response(response: Any) -> dict[str, Any]:
    return {
        "session_id": response.session_id,
        "job_id": response.job_id,
        "base_version": response.base_version,
        "working_version": response.working_version,
        "autosave_enabled": response.autosave_enabled,
        "history_index": response.history_index,
        "segments": response.segments,
        "speaker_labels": response.speaker_labels,
        "operation_log": response.operation_log,
        "review_status": response.review_status,
        "is_final": response.is_final,
    }


def map_transcript_status_response(response: Any) -> dict[str, Any]:
    return {
        "job_id": response.job_id,
        "review_status": response.review_status,
        "is_final": response.is_final,
        "final_set_by": response.final_set_by,
        "final_set_at": response.final_set_at,
        "updated_at": response.updated_at,
    }


def map_export_response(response: Any) -> dict[str, Any]:
    return {"export_id": response.export_id, "status": response.status}


def create_fastapi_app(
    *,
    settings: FastAPIAdapterSettings,
    token_verifier: Callable[[str], dict[str, Any]],
    job_repository: Any,
    upload_session_factory: Any,
    audit_log: Any,
    idempotency_store: Any,
    complete_upload_idempotency_store: Any,
    object_storage: Any,
    outbox: Any,
    queue_policy: QueueSelectionPolicy | None = None,
    transcript_repository: Any | None = None,
    transcript_correction_store: Any | None = None,
    export_artifact_store: Any | None = None,
    checkpoint_store: Any | None = None,
    worker_artifact_store: Any | None = None,
    transcription_settings_store: Any | None = None,
    media_base_url: str | None = None,
    media_bucket: str | None = None,
):
    try:
        from fastapi import FastAPI, Header, HTTPException
        from pydantic import BaseModel, Field
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI/Pydantic sind nicht installiert. Bitte Runtime-Abhängigkeiten bereitstellen."
        ) from exc

    app = FastAPI(title="EvidoX API", version="v1")
    queue_policy = queue_policy or QueueSelectionPolicy()

    class JobCreatePayload(BaseModel):
        filename: str = Field(min_length=1, max_length=255)
        content_type: str
        size_bytes: int
        retention_months: int
        language: str = Field(default="de")

    class CompleteUploadPayload(BaseModel):
        upload_session_id: str = Field(min_length=1)
        object_key: str = Field(min_length=1)
        checksum_sha256: str = Field(min_length=64, max_length=64)


    class TranscriptUpdateSegment(BaseModel):
        segment_id: str = Field(min_length=1)
        speaker: str = Field(min_length=1, max_length=32)
        text: str = Field(min_length=1, max_length=5000)

    class TranscriptUpdatePayload(BaseModel):
        base_version: int
        segments: list[TranscriptUpdateSegment]
        edit_reason: str = Field(min_length=3, max_length=255)

    class TranscriptSpeakerLabelsUpdatePayload(BaseModel):
        base_version: int
        speaker_labels: dict[str, str]
        edit_reason: str = Field(min_length=3, max_length=255)

    class TranscriptStatusUpdatePayload(BaseModel):
        review_status: str | None = Field(default=None, min_length=2, max_length=64)
        is_final: bool | None = None

    class CorrectionSessionCreatePayload(BaseModel):
        base_version: int | None = None
        autosave_enabled: bool = False

    class CorrectionSessionUpdatePayload(BaseModel):
        autosave_enabled: bool

    class CorrectionSessionOperation(BaseModel):
        type: str = Field(min_length=1, max_length=64)
        segment_id: str | None = None
        speaker: str | None = None
        start_char: int | None = None
        end_char: int | None = None
        query: str | None = None
        replace: str | None = None
        replace_all: bool | None = None
        segments: list[dict[str, Any]] | None = None

    class CorrectionSessionApplyPayload(BaseModel):
        operations: list[CorrectionSessionOperation] = Field(min_length=1)
        autosave_enabled: bool | None = None

    class CorrectionSessionCommitPayload(BaseModel):
        base_version: int
        edit_reason: str = Field(min_length=3, max_length=255)

    class ExportPayload(BaseModel):
        format: str
        transcript_version: int

    def _http_error(status_code: int, error_code: str, correlation_id: str | None = None) -> HTTPException:
        return HTTPException(
            status_code=status_code,
            detail={"error_code": error_code, "correlation_id": correlation_id or str(uuid4())},
        )

    def _correction_error_status(error_code: str) -> int:
        if error_code == "transcript.correction_session_not_found":
            return 404
        if error_code == "transcript.correction_session_forbidden":
            return 403
        if error_code == "transcript.not_found":
            return 404
        if error_code == "transcript.correction_unavailable":
            return 503
        return 422

    def _require_auth(authorization: str | None, *, required_roles: set[str] | None = None):
        if not authorization or not authorization.lower().startswith("bearer "):
            raise _http_error(401, "auth.invalid_token")
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = token_verifier(token)
            return authorize_request(
                claims=claims,
                expected_issuer=settings.expected_issuer,
                expected_audience=settings.expected_audience,
                now=int(claims.get("now", int(datetime.now(tz=timezone.utc).timestamp()))),
                required_roles=required_roles or {"user", "reviewer", "admin"},
            )
        except AuthzError:
            raise
        except Exception as exc:
            raise _http_error(401, "auth.invalid_token") from exc

    @app.post("/api/v1/jobs")
    def post_jobs(
        payload: JobCreatePayload,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            if not idempotency_key:
                raise ValidationError("job.validation.idempotency_key", "Missing Idempotency-Key header")

            result = create_job(
                CreateJobInput(
                    filename=payload.filename,
                    content_type=payload.content_type,
                    size_bytes=payload.size_bytes,
                    retention_months=payload.retention_months,
                    idempotency_key=idempotency_key,
                    language=payload.language,
                ),
                actor_context=auth_context,
                job_repository=job_repository,
                upload_session_factory=upload_session_factory,
                audit_log=audit_log,
                idempotency_store=idempotency_store,
            )
            return map_create_job_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except ValidationError as exc:
            raise _http_error(422, exc.error_code) from exc

    @app.get("/api/v1/jobs")
    def get_jobs(
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            list_for_tenant = getattr(job_repository, "list_for_tenant", None)
            if not callable(list_for_tenant):
                raise _http_error(503, "jobs.unavailable")
            rows = list_for_tenant(auth_context.tenant_id)
            return map_jobs_list_response(rows)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc

    @app.post("/api/v1/jobs/{job_id}/complete-upload")
    def post_complete_upload(
        job_id: str,
        payload: CompleteUploadPayload,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            if not idempotency_key:
                raise CompleteUploadValidationError(
                    "job.complete_upload.invalid_idempotency_key",
                    "Missing Idempotency-Key header",
                )

            result = complete_upload(
                CompleteUploadInput(
                    job_id=job_id,
                    upload_session_id=payload.upload_session_id,
                    object_key=payload.object_key,
                    checksum_sha256=payload.checksum_sha256,
                    idempotency_key=idempotency_key,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_store=job_repository,
                object_storage=object_storage,
                outbox=outbox,
                idempotency_store=complete_upload_idempotency_store,
                queue_policy=queue_policy,
                transcription_settings_store=transcription_settings_store,
            )
            return map_complete_upload_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except CompleteUploadValidationError as exc:
            status_code = 404 if exc.error_code == "job.not_found" else 422
            raise _http_error(status_code, exc.error_code) from exc

    @app.get("/api/v1/admin/transcription-settings")
    def get_admin_transcription_settings(
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcription_settings_store is None:
            raise _http_error(503, "transcription_settings.unavailable")
        try:
            auth_context = _require_auth(authorization, required_roles={"admin"})
            return get_transcription_settings(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                settings_store=transcription_settings_store,
                audit_log=audit_log,
            )
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc

    @app.put("/api/v1/admin/transcription-settings")
    def put_admin_transcription_settings(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcription_settings_store is None:
            raise _http_error(503, "transcription_settings.unavailable")
        try:
            auth_context = _require_auth(authorization, required_roles={"admin"})
            return update_transcription_settings(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                payload=payload,
                settings_store=transcription_settings_store,
                audit_log=audit_log,
            )
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptionSettingsValidationError as exc:
            status_code = 503 if exc.error_code == "transcription_settings.unavailable" else 422
            raise _http_error(status_code, exc.error_code) from exc

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(
        job_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            result = get_job_status(job_id=job_id, tenant_id=auth_context.tenant_id, job_store=job_repository)
            return map_job_status_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except JobStatusNotFoundError as exc:
            raise _http_error(404, exc.error_code) from exc

    @app.get("/api/v1/jobs/{job_id}/media-source")
    def get_job_media_source(
        job_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            get_for_tenant = getattr(job_repository, "get", None)
            if not callable(get_for_tenant):
                raise _http_error(503, "jobs.unavailable")
            row = get_for_tenant(auth_context.tenant_id, job_id)
            if row is None:
                raise _http_error(404, "job.not_found")
            payload = map_job_media_source_response(
                job_id=job_id,
                row=row,
                media_base_url=media_base_url,
                media_bucket=media_bucket,
            )
            if payload is None:
                raise _http_error(503, "media_source.unavailable")
            return payload
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc

    @app.post("/api/v1/jobs/{job_id}/pause")
    def post_job_pause(
        job_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            pause_job(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                job_store=job_repository,
                outbox=outbox,
                audit_log=audit_log,
            )
            result = get_job_status(job_id=job_id, tenant_id=auth_context.tenant_id, job_store=job_repository)
            return map_job_status_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except JobLifecycleError as exc:
            raise _http_error(exc.status_code, exc.error_code) from exc
        except JobStatusNotFoundError as exc:
            raise _http_error(404, exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/resume")
    def post_job_resume(
        job_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            resume_job(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                job_store=job_repository,
                outbox=outbox,
                audit_log=audit_log,
                queue_policy=queue_policy,
            )
            result = get_job_status(job_id=job_id, tenant_id=auth_context.tenant_id, job_store=job_repository)
            return map_job_status_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except JobLifecycleError as exc:
            raise _http_error(exc.status_code, exc.error_code) from exc
        except JobStatusNotFoundError as exc:
            raise _http_error(404, exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def post_job_cancel(
        job_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            cancel_job(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                job_store=job_repository,
                outbox=outbox,
                audit_log=audit_log,
            )
            result = get_job_status(job_id=job_id, tenant_id=auth_context.tenant_id, job_store=job_repository)
            return map_job_status_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except JobLifecycleError as exc:
            raise _http_error(exc.status_code, exc.error_code) from exc
        except JobStatusNotFoundError as exc:
            raise _http_error(404, exc.error_code) from exc

    @app.delete("/api/v1/jobs/{job_id}")
    def delete_job_endpoint(
        job_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization)
            delete_job(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                job_store=job_repository,
                outbox=outbox,
                object_storage=object_storage,
                audit_log=audit_log,
                checkpoint_store=checkpoint_store,
                artifact_store=worker_artifact_store,
                transcript_store=transcript_repository,
            )
            result = get_job_status(job_id=job_id, tenant_id=auth_context.tenant_id, job_store=job_repository)
            return map_job_status_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except JobLifecycleError as exc:
            raise _http_error(exc.status_code, exc.error_code) from exc
        except JobStatusNotFoundError as exc:
            raise _http_error(404, exc.error_code) from exc

    @app.get("/api/v1/jobs/{job_id}/transcript")
    def get_job_transcript(
        job_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_repository is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = get_transcript(tenant_id=auth_context.tenant_id, job_id=job_id, transcript_repo=transcript_repository)
            payload = map_transcript_response(result)
            if transcript_correction_store is not None:
                status = get_transcript_status(
                    tenant_id=auth_context.tenant_id,
                    job_id=job_id,
                    correction_store=transcript_correction_store,
                )
                payload.update(
                    {
                        "review_status": status.review_status,
                        "is_final": status.is_final,
                        "final_set_by": status.final_set_by,
                        "final_set_at": status.final_set_at,
                        "status_updated_at": status.updated_at,
                    }
                )
            return payload
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            status_code = 404 if exc.error_code == "transcript.not_found" else 422
            raise _http_error(status_code, exc.error_code) from exc

    @app.put("/api/v1/jobs/{job_id}/transcript")
    def put_job_transcript(
        job_id: str,
        payload: TranscriptUpdatePayload,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_repository is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = update_transcript(
                UpdateTranscriptInput(
                    job_id=job_id,
                    base_version=payload.base_version,
                    segments=[item.model_dump() for item in payload.segments],
                    edit_reason=payload.edit_reason,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                transcript_repo=transcript_repository,
                audit_log=audit_log,
            )
            return map_transcript_update_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptConflictError as exc:
            raise _http_error(409, exc.error_code) from exc
        except TranscriptValidationError as exc:
            status_code = 404 if exc.error_code == "transcript.not_found" else 422
            raise _http_error(status_code, exc.error_code) from exc

    @app.put("/api/v1/jobs/{job_id}/transcript/speaker-labels")
    def put_job_transcript_speaker_labels(
        job_id: str,
        payload: TranscriptSpeakerLabelsUpdatePayload,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_repository is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = update_transcript_speaker_labels(
                UpdateTranscriptSpeakerLabelsInput(
                    job_id=job_id,
                    base_version=payload.base_version,
                    speaker_labels=payload.speaker_labels,
                    edit_reason=payload.edit_reason,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                transcript_repo=transcript_repository,
                audit_log=audit_log,
            )
            return map_transcript_update_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptConflictError as exc:
            raise _http_error(409, exc.error_code) from exc
        except TranscriptValidationError as exc:
            status_code = 404 if exc.error_code == "transcript.not_found" else 422
            raise _http_error(status_code, exc.error_code) from exc

    @app.patch("/api/v1/jobs/{job_id}/transcript/status")
    def patch_job_transcript_status(
        job_id: str,
        payload: TranscriptStatusUpdatePayload,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        if transcript_repository is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.unavailable"})
        try:
            auth_context = _require_auth(authorization, required_roles={"reviewer", "admin"})
            result = update_transcript_status(
                TranscriptStatusUpdateInput(
                    job_id=job_id,
                    review_status=payload.review_status,
                    is_final=payload.is_final,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                transcript_repo=transcript_repository,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_transcript_status_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/transcript/correction-sessions")
    def post_correction_session(
        job_id: str,
        payload: CorrectionSessionCreatePayload,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_repository is None or transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = create_correction_session(
                CorrectionSessionCreateInput(
                    job_id=job_id,
                    base_version=payload.base_version,
                    autosave_enabled=payload.autosave_enabled,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                transcript_repo=transcript_repository,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_correction_session_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptConflictError as exc:
            raise _http_error(409, exc.error_code) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.get("/api/v1/jobs/{job_id}/transcript/correction-sessions/{session_id}")
    def get_correction_session_endpoint(
        job_id: str,
        session_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = get_correction_session(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                session_id=session_id,
                correction_store=transcript_correction_store,
            )
            return map_correction_session_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.patch("/api/v1/jobs/{job_id}/transcript/correction-sessions/{session_id}")
    def patch_correction_session_endpoint(
        job_id: str,
        session_id: str,
        payload: CorrectionSessionUpdatePayload,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = set_correction_session_options(
                CorrectionSessionOptionsInput(
                    job_id=job_id,
                    session_id=session_id,
                    autosave_enabled=payload.autosave_enabled,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_correction_session_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/transcript/correction-sessions/{session_id}/operations")
    def post_correction_session_operations(
        job_id: str,
        session_id: str,
        payload: CorrectionSessionApplyPayload,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = apply_correction_operations(
                CorrectionSessionApplyInput(
                    job_id=job_id,
                    session_id=session_id,
                    operations=[item.model_dump(exclude_none=True) for item in payload.operations],
                    autosave_enabled=payload.autosave_enabled,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_correction_session_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/transcript/correction-sessions/{session_id}/undo")
    def post_correction_session_undo(
        job_id: str,
        session_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = undo_correction_session(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                session_id=session_id,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_correction_session_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/transcript/correction-sessions/{session_id}/redo")
    def post_correction_session_redo(
        job_id: str,
        session_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = redo_correction_session(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                session_id=session_id,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_correction_session_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/transcript/correction-sessions/{session_id}/discard")
    def post_correction_session_discard(
        job_id: str,
        session_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = discard_correction_session(
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                job_id=job_id,
                session_id=session_id,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_correction_session_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/transcript/correction-sessions/{session_id}/commit")
    def post_correction_session_commit(
        job_id: str,
        session_id: str,
        payload: CorrectionSessionCommitPayload,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_repository is None or transcript_correction_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "transcript.correction_unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = commit_correction_session(
                CorrectionSessionCommitInput(
                    job_id=job_id,
                    session_id=session_id,
                    base_version=payload.base_version,
                    edit_reason=payload.edit_reason,
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                transcript_repo=transcript_repository,
                correction_store=transcript_correction_store,
                audit_log=audit_log,
            )
            return map_transcript_update_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except TranscriptConflictError as exc:
            raise _http_error(409, exc.error_code) from exc
        except TranscriptValidationError as exc:
            raise _http_error(_correction_error_status(exc.error_code), exc.error_code) from exc

    @app.post("/api/v1/jobs/{job_id}/export")
    def post_job_export(
        job_id: str,
        payload: ExportPayload,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        if transcript_repository is None or export_artifact_store is None:
            raise HTTPException(status_code=503, detail={"error_code": "export.unavailable"})
        try:
            auth_context = _require_auth(authorization)
            result = queue_export(
                ExportRequestInput(
                    job_id=job_id,
                    transcript_version=payload.transcript_version,
                    format=payload.format,
                    idempotency_key=idempotency_key or "",
                ),
                tenant_id=auth_context.tenant_id,
                actor_id=auth_context.actor_id,
                transcript_repo=transcript_repository,
                export_store=export_artifact_store,
                audit_log=audit_log,
            )
            return map_export_response(result)
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc
        except ExportValidationError as exc:
            status_code = 404 if exc.error_code == "export.transcript_not_found" else 422
            raise _http_error(status_code, exc.error_code) from exc

    @app.get("/api/v1/audit")
    def get_audit_events(
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    ) -> dict[str, Any]:
        del x_correlation_id
        try:
            auth_context = _require_auth(authorization, required_roles={"admin"})
            list_for_tenant = getattr(audit_log, "list_for_tenant", None)
            if callable(list_for_tenant):
                events = list_for_tenant(tenant_id=auth_context.tenant_id, limit=200)
            else:
                list_all = getattr(audit_log, "list_all", None)
                if callable(list_all):
                    events = [item for item in list_all(limit=1000) if item.get("tenant_id") == auth_context.tenant_id][:200]
                else:
                    events = []
            return {"events": events}
        except AuthzError as exc:
            raise _http_error(exc.status_code, exc.error_code, exc.correlation_id) from exc


    return app
