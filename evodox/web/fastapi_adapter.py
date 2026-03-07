from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from evodox.auth.context import AuthzError, authorize_request
from evodox.jobs.complete_upload_service import (
    CompleteUploadInput,
    CompleteUploadValidationError,
    QueueSelectionPolicy,
    complete_upload,
)
from evodox.jobs.create_service import CreateJobInput, ValidationError, create_job
from evodox.jobs.get_job_status_service import JobStatusNotFoundError, get_job_status


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

    class CompleteUploadPayload(BaseModel):
        upload_session_id: str = Field(min_length=1)
        object_key: str = Field(min_length=1)
        checksum_sha256: str = Field(min_length=64, max_length=64)

    def _require_auth(authorization: str | None):
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail={"error_code": "auth.invalid_token"})
        token = authorization.split(" ", 1)[1].strip()
        claims = token_verifier(token)
        return authorize_request(
            claims=claims,
            expected_issuer=settings.expected_issuer,
            expected_audience=settings.expected_audience,
            now=claims.get("now", 0),
            required_roles={"user", "reviewer", "admin"},
        )

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
                ),
                actor_context=auth_context,
                job_repository=job_repository,
                upload_session_factory=upload_session_factory,
                audit_log=audit_log,
                idempotency_store=idempotency_store,
            )
            return map_create_job_response(result)
        except AuthzError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"error_code": exc.error_code, "correlation_id": exc.correlation_id},
            ) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail={"error_code": exc.error_code}) from exc

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
            )
            return map_complete_upload_response(result)
        except AuthzError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"error_code": exc.error_code, "correlation_id": exc.correlation_id},
            ) from exc
        except CompleteUploadValidationError as exc:
            status_code = 404 if exc.error_code == "job.not_found" else 422
            raise HTTPException(status_code=status_code, detail={"error_code": exc.error_code}) from exc

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
            raise HTTPException(
                status_code=exc.status_code,
                detail={"error_code": exc.error_code, "correlation_id": exc.correlation_id},
            ) from exc
        except JobStatusNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"error_code": exc.error_code}) from exc

    return app
