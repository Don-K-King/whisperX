from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
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


def map_transcript_response(response: Any) -> dict[str, Any]:
    return {
        "job_id": response.job_id,
        "version": response.version,
        "segments": response.segments,
        "speaker_labels": dict(getattr(response, "speaker_labels", {}) or {}),
    }


def map_transcript_update_response(response: Any) -> dict[str, Any]:
    return {"job_id": response.job_id, "version": response.version, "saved_at": response.saved_at}


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
    export_artifact_store: Any | None = None,
    checkpoint_store: Any | None = None,
    worker_artifact_store: Any | None = None,
    transcription_settings_store: Any | None = None,
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

    class ExportPayload(BaseModel):
        format: str
        transcript_version: int

    def _http_error(status_code: int, error_code: str, correlation_id: str | None = None) -> HTTPException:
        return HTTPException(
            status_code=status_code,
            detail={"error_code": error_code, "correlation_id": correlation_id or str(uuid4())},
        )

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
            return map_transcript_response(result)
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
