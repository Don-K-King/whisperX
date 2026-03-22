from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .transcription_settings_service import (
    InMemoryTenantTranscriptionSettingsStore,
    safe_worker_decoding_options,
)

ALLOWED_SOURCE_STATUSES = frozenset({"upload_pending", "uploaded", "queued"})
CHECKSUM_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


@dataclass(frozen=True)
class CompleteUploadInput:
    job_id: str
    upload_session_id: str
    object_key: str
    checksum_sha256: str
    idempotency_key: str


@dataclass(frozen=True)
class CompleteUploadResponse:
    job_id: str
    status: str
    queue: str


@dataclass(frozen=True)
class CompleteUploadIdempotencyRecord:
    tenant_id: str
    payload_hash: str
    response: CompleteUploadResponse


class CompleteUploadValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class QueueSelectionPolicy:
    def select_queue(self, *, content_type: str, size_bytes: int) -> str:
        if content_type.startswith("video/") or content_type.startswith("audio/") or size_bytes >= 250_000_000:
            return "gpu-standard"
        return "cpu-short"


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], dict[str, Any]] = {}

    def add_job(self, job: dict[str, Any]) -> None:
        self._jobs[(job["tenant_id"], job["job_id"])] = dict(job)

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        item = self._jobs.get((tenant_id, job_id))
        return None if item is None else dict(item)

    def set_status(self, tenant_id: str, job_id: str, status: str) -> None:
        key = (tenant_id, job_id)
        if key not in self._jobs:
            raise KeyError("job not found")
        self._jobs[key]["status"] = status

    def mark_queued(
        self,
        tenant_id: str,
        job_id: str,
        *,
        object_key: str,
        checksum_sha256: str,
        upload_session_id: str,
        transcription_options: dict[str, Any] | None = None,
    ) -> None:
        key = (tenant_id, job_id)
        if key not in self._jobs:
            raise KeyError("job not found")
        self._jobs[key]["status"] = "queued"
        self._jobs[key]["progress"] = 5
        self._jobs[key]["object_key"] = object_key
        self._jobs[key]["checksum_sha256"] = checksum_sha256
        self._jobs[key]["upload_session_id"] = upload_session_id
        if transcription_options is not None:
            self._jobs[key]["transcription_options"] = dict(transcription_options)


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self._objects: dict[str, str] = {}

    def put(self, object_key: str, *, checksum_sha256: str) -> None:
        self._objects[object_key] = checksum_sha256

    def exists_with_checksum(self, object_key: str, checksum_sha256: str) -> bool:
        return self._objects.get(object_key) == checksum_sha256


class InMemoryOutbox:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


class InMemoryCompleteUploadIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], CompleteUploadIdempotencyRecord] = {}

    def get(self, tenant_id: str, key: str) -> CompleteUploadIdempotencyRecord | None:
        return self._records.get((tenant_id, key))

    def put(self, tenant_id: str, key: str, record: CompleteUploadIdempotencyRecord) -> None:
        self._records[(tenant_id, key)] = record


def complete_upload(
    request: CompleteUploadInput,
    *,
    tenant_id: str,
    actor_id: str,
    job_store: Any,
    object_storage: Any,
    outbox: Any,
    idempotency_store: Any,
    queue_policy: QueueSelectionPolicy,
    transcription_settings_store: Any | None = None,
) -> CompleteUploadResponse:
    _validate_request(request, tenant_id)

    payload_hash = _payload_hash(request)
    existing = idempotency_store.get(tenant_id, request.idempotency_key)
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise CompleteUploadValidationError(
                "job.complete_upload.idempotency_conflict",
                "Idempotency-Key wurde mit anderem Payload wiederverwendet.",
            )
        return existing.response

    job = job_store.get(tenant_id, request.job_id)
    if job is None:
        raise CompleteUploadValidationError("job.not_found", "Job wurde nicht gefunden.")

    if job.get("status") not in ALLOWED_SOURCE_STATUSES:
        raise CompleteUploadValidationError("job.complete_upload.invalid_state", "Ungültiger Job-Status für complete-upload.")

    if not object_storage.exists_with_checksum(request.object_key, request.checksum_sha256):
        raise CompleteUploadValidationError(
            "job.complete_upload.object_missing",
            "Upload-Objekt fehlt oder Prüfsumme stimmt nicht.",
        )

    queue_name = queue_policy.select_queue(
        content_type=str(job.get("content_type", "")),
        size_bytes=int(job.get("size_bytes", 0)),
    )
    transcription_options = _resolve_transcription_options(
        tenant_id=tenant_id,
        transcription_settings_store=transcription_settings_store,
    )

    mark_queued = getattr(job_store, "mark_queued", None)
    if callable(mark_queued):
        try:
            mark_queued(
                tenant_id,
                request.job_id,
                object_key=request.object_key,
                checksum_sha256=request.checksum_sha256,
                upload_session_id=request.upload_session_id,
                transcription_options=transcription_options,
            )
        except TypeError:
            mark_queued(
                tenant_id,
                request.job_id,
                object_key=request.object_key,
                checksum_sha256=request.checksum_sha256,
                upload_session_id=request.upload_session_id,
            )
    else:
        job_store.set_status(tenant_id, request.job_id, "queued")
    outbox.append(
        {
            "event_type": "job.queued",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "queue": queue_name,
            "upload_session_id": request.upload_session_id,
            "object_key": request.object_key,
            "checksum_sha256": request.checksum_sha256,
            "transcription_options": transcription_options,
        }
    )

    response = CompleteUploadResponse(job_id=request.job_id, status="queued", queue=queue_name)
    idempotency_store.put(
        tenant_id,
        request.idempotency_key,
        CompleteUploadIdempotencyRecord(tenant_id=tenant_id, payload_hash=payload_hash, response=response),
    )
    return response


def _validate_request(request: CompleteUploadInput, tenant_id: str) -> None:
    if not isinstance(request.idempotency_key, str) or len(request.idempotency_key.strip()) < 8:
        raise CompleteUploadValidationError(
            "job.complete_upload.invalid_idempotency_key", "Idempotency-Key ist erforderlich (>=8 Zeichen)."
        )

    if not isinstance(request.upload_session_id, str) or len(request.upload_session_id.strip()) == 0:
        raise CompleteUploadValidationError(
            "job.complete_upload.invalid_upload_session", "upload_session_id ist erforderlich."
        )

    if not CHECKSUM_PATTERN.fullmatch(request.checksum_sha256 or ""):
        raise CompleteUploadValidationError("job.complete_upload.invalid_checksum", "checksum_sha256 ist ungültig.")

    object_key = request.object_key or ""
    if not object_key.startswith(f"tenant/{tenant_id}/{request.job_id}/"):
        raise CompleteUploadValidationError(
            "job.complete_upload.invalid_object_key", "object_key passt nicht zum Tenant/Job-Kontext."
        )


def _payload_hash(request: CompleteUploadInput) -> str:
    payload = (
        f"{request.job_id}|{request.upload_session_id}|{request.object_key}|"
        f"{request.checksum_sha256}|{request.idempotency_key}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_transcription_options(*, tenant_id: str, transcription_settings_store: Any | None) -> dict[str, Any]:
    store = transcription_settings_store
    if store is None:
        return safe_worker_decoding_options(None)
    getter = getattr(store, "get", None)
    if not callable(getter):
        return safe_worker_decoding_options(None)
    row = getter(tenant_id)
    if not isinstance(row, dict):
        return safe_worker_decoding_options(None)
    return safe_worker_decoding_options(row.get("decoding_options"))
