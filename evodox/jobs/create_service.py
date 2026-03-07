from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import unicodedata
from uuid import uuid4

ALLOWED_UPLOAD_CONTENT_TYPES = frozenset({
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
})
MAX_UPLOAD_SIZE_BYTES = 21_474_836_480
MIN_RETENTION_MONTHS = 1
MAX_RETENTION_MONTHS = 36


@dataclass(frozen=True)
class CreateJobInput:
    filename: str
    content_type: str
    size_bytes: int
    retention_months: int
    idempotency_key: str


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    tenant_id: str
    actor_id: str
    filename: str
    content_type: str
    size_bytes: int
    retention_months: int
    status: str = "upload_pending"


@dataclass(frozen=True)
class UploadSession:
    session_id: str
    object_key: str
    presigned_url: str
    expires_at: str


@dataclass(frozen=True)
class CreateJobResponse:
    job_id: str
    tenant_id: str
    status: str
    upload: UploadSession


@dataclass(frozen=True)
class IdempotencyRecord:
    tenant_id: str
    payload_hash: str
    response: CreateJobResponse


class ValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class InMemoryJobRepository:
    def __init__(self) -> None:
        self.jobs: list[JobRecord] = []

    def create(self, job: JobRecord) -> None:
        self.jobs.append(job)


class InMemoryUploadSessionFactory:
    def __init__(self) -> None:
        self.created: list[UploadSession] = []

    def create_session(self, *, tenant_id: str, job_id: str, filename: str) -> UploadSession:
        object_key = f"tenant/{tenant_id}/{job_id}/{filename}"
        session = UploadSession(
            session_id=f"up_{uuid4().hex[:12]}",
            object_key=object_key,
            presigned_url=f"https://minio.local/upload/{object_key}",
            expires_at=(datetime.now(tz=timezone.utc) + timedelta(minutes=15)).isoformat(),
        )
        self.created.append(session)
        return session


class InMemoryAuditLog:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def append(self, event: dict[str, str]) -> None:
        self.events.append(event)


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], IdempotencyRecord] = {}

    def get(self, tenant_id: str, key: str) -> IdempotencyRecord | None:
        return self.records.get((tenant_id, key))

    def put(self, tenant_id: str, key: str, record: IdempotencyRecord) -> None:
        self.records[(tenant_id, key)] = record


@dataclass(frozen=True)
class ActorContext:
    actor_id: str
    tenant_id: str


def create_job(
    request: CreateJobInput,
    *,
    actor_context: ActorContext,
    job_repository: InMemoryJobRepository,
    upload_session_factory: InMemoryUploadSessionFactory,
    audit_log: InMemoryAuditLog,
    idempotency_store: InMemoryIdempotencyStore,
) -> CreateJobResponse:
    _validate_create_job_request(request)

    payload_hash = _payload_hash(request)
    existing = idempotency_store.get(actor_context.tenant_id, request.idempotency_key)
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise ValidationError("job.idempotency.conflict", "Idempotency-Key was reused with a different payload.")
        return existing.response

    job_id = f"job_{uuid4().hex[:12]}"
    job = JobRecord(
        job_id=job_id,
        tenant_id=actor_context.tenant_id,
        actor_id=actor_context.actor_id,
        filename=request.filename,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
        retention_months=request.retention_months,
    )
    upload_session = upload_session_factory.create_session(
        tenant_id=actor_context.tenant_id,
        job_id=job_id,
        filename=request.filename,
    )

    response = CreateJobResponse(
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        status=job.status,
        upload=upload_session,
    )

    job_repository.create(job)
    audit_log.append(
        {
            "action": "job.create",
            "tenant_id": actor_context.tenant_id,
            "actor_id": actor_context.actor_id,
            "job_id": job.job_id,
            "idempotency_key": request.idempotency_key,
        }
    )
    idempotency_store.put(
        actor_context.tenant_id,
        request.idempotency_key,
        IdempotencyRecord(
            tenant_id=actor_context.tenant_id,
            payload_hash=payload_hash,
            response=response,
        ),
    )

    return response


def _validate_create_job_request(request: CreateJobInput) -> None:
    if request.content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise ValidationError("job.validation.content_type", "Unsupported content type.")

    if not isinstance(request.size_bytes, int) or request.size_bytes <= 0 or request.size_bytes > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError("job.validation.size", "Upload size is out of allowed range.")

    if (
        not isinstance(request.retention_months, int)
        or request.retention_months < MIN_RETENTION_MONTHS
        or request.retention_months > MAX_RETENTION_MONTHS
    ):
        raise ValidationError("job.validation.retention", "Retention months must be within 1..36.")

    if not isinstance(request.filename, str) or len(request.filename) == 0 or len(request.filename) > 255:
        raise ValidationError("job.validation.filename", "Filename must be provided and <=255 chars.")

    normalized_filename = unicodedata.normalize("NFC", request.filename)
    if any(ord(ch) < 32 for ch in normalized_filename) or "\x00" in normalized_filename:
        raise ValidationError("job.validation.filename", "Filename contains forbidden control characters.")

    if "/" in normalized_filename or "\\" in normalized_filename:
        raise ValidationError("job.validation.filename", "Filename must not contain path separators.")

    if not isinstance(request.idempotency_key, str) or len(request.idempotency_key.strip()) < 8:
        raise ValidationError("job.validation.idempotency_key", "Idempotency-Key is required and must be >= 8 chars.")


def _payload_hash(request: CreateJobInput) -> str:
    payload = (
        f"{request.filename}|{request.content_type}|{request.size_bytes}|"
        f"{request.retention_months}|{request.idempotency_key}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
