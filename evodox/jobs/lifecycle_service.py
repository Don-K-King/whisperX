from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from .complete_upload_service import QueueSelectionPolicy
from .progress import derive_progress
from .transcription_settings_service import safe_worker_decoding_options


PAUSE_IDEMPOTENT_STATUSES = frozenset({"pause_requested", "paused"})
DELETE_IDEMPOTENT_STATUSES = frozenset({"deleted"})
DELETE_ALLOWED_STATUSES = frozenset(
    {
        "upload_pending",
        "uploaded",
        "queued",
        "processing",
        "pause_requested",
        "cancel_requested",
        "paused",
        "failed_retryable",
        "failed_terminal",
        "completed",
        "canceled",
    }
)
RESUME_ALLOWED_STATUSES = frozenset({"paused", "failed_retryable"})
CANCEL_IDEMPOTENT_STATUSES = frozenset({"cancel_requested", "canceled"})
CANCEL_IMMEDIATE_STATUSES = frozenset({"queued", "paused"})
CANCEL_REQUESTABLE_STATUSES = frozenset({"processing", "pause_requested"})


class JobLifecycleError(Exception):
    def __init__(self, *, status_code: int, error_code: str, message: str):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


def pause_job(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    job_store: Any,
    outbox: Any,
    audit_log: Any,
) -> str:
    del outbox
    job = _require_job(tenant_id=tenant_id, job_id=job_id, job_store=job_store)
    status = str(job.get("status") or "")

    if status in PAUSE_IDEMPOTENT_STATUSES:
        return status
    if status == "queued":
        _set_status(job_store, tenant_id, job_id, "paused", progress=5)
        _append_audit(audit_log, action="job.pause", tenant_id=tenant_id, actor_id=actor_id, job_id=job_id)
        return "paused"
    if status == "processing":
        current_progress = derive_progress(status=status, raw_progress=job.get("progress"))
        _set_status(job_store, tenant_id, job_id, "pause_requested", progress=max(20, current_progress))
        _append_audit(audit_log, action="job.pause_requested", tenant_id=tenant_id, actor_id=actor_id, job_id=job_id)
        return "pause_requested"

    raise JobLifecycleError(
        status_code=409,
        error_code="job.pause.invalid_state",
        message="Job kann in diesem Status nicht pausiert werden.",
    )


def resume_job(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    job_store: Any,
    outbox: Any,
    audit_log: Any,
    queue_policy: QueueSelectionPolicy | None = None,
) -> str:
    job = _require_job(tenant_id=tenant_id, job_id=job_id, job_store=job_store)
    status = str(job.get("status") or "")

    if status == "queued":
        return "queued"
    if status not in RESUME_ALLOWED_STATUSES:
        raise JobLifecycleError(
            status_code=409,
            error_code="job.resume.invalid_state",
            message="Job kann in diesem Status nicht fortgesetzt werden.",
        )

    object_key = str(job.get("object_key") or "")
    if not object_key:
        raise JobLifecycleError(
            status_code=422,
            error_code="job.resume.object_key_missing",
            message="Resume setzt ein vorhandenes object_key voraus.",
        )
    checksum_sha256 = str(job.get("checksum_sha256") or "")
    upload_session_id = str(job.get("upload_session_id") or "")
    transcription_options = _extract_transcription_options(job)

    _set_status(job_store, tenant_id, job_id, "queued", progress=5)
    queue = (queue_policy or QueueSelectionPolicy()).select_queue(
        content_type=str(job.get("content_type") or ""),
        size_bytes=int(job.get("size_bytes") or 0),
    )
    outbox.append(
        {
            "event_id": f"evt_resume_{job_id}_{uuid4().hex}",
            "event_type": "job.queued",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": job_id,
            "queue": queue,
            "upload_session_id": upload_session_id,
            "object_key": object_key,
            "checksum_sha256": checksum_sha256,
            "transcription_options": transcription_options,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    )
    _append_audit(audit_log, action="job.resume", tenant_id=tenant_id, actor_id=actor_id, job_id=job_id)
    return "queued"


def delete_job(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    job_store: Any,
    outbox: Any,
    object_storage: Any,
    audit_log: Any,
    checkpoint_store: Any | None = None,
    artifact_store: Any | None = None,
    transcript_store: Any | None = None,
) -> str:
    job = _require_job(tenant_id=tenant_id, job_id=job_id, job_store=job_store)
    status = str(job.get("status") or "")

    if status in DELETE_IDEMPOTENT_STATUSES:
        return "deleted"
    if status not in DELETE_ALLOWED_STATUSES:
        raise JobLifecycleError(
            status_code=409,
            error_code="job.delete.invalid_state",
            message="Job kann in diesem Status nicht geloescht werden.",
        )

    object_prefix = _object_prefix_for_job(tenant_id=tenant_id, job_id=job_id, object_key=job.get("object_key"))
    delete_prefix = getattr(object_storage, "delete_prefix", None)
    if callable(delete_prefix):
        deleted = bool(delete_prefix(tenant_id=tenant_id, object_prefix=object_prefix))
        if not deleted:
            raise JobLifecycleError(
                status_code=503,
                error_code="job.delete.storage_failed",
                message="Storage-Loeschung fehlgeschlagen.",
            )

    mark_deleted = getattr(job_store, "mark_deleted", None)
    if callable(mark_deleted):
        mark_deleted(tenant_id, job_id, actor_id=actor_id)
    else:
        _set_status(job_store, tenant_id, job_id, "deleted", progress=100)

    _prune_pending_outbox(outbox, tenant_id=tenant_id, job_id=job_id, error_code="job.deleted")
    _cleanup_job_internal_state(
        tenant_id=tenant_id,
        job_id=job_id,
        checkpoint_store=checkpoint_store,
        artifact_store=artifact_store,
        transcript_store=transcript_store,
    )

    _append_audit(
        audit_log,
        action="job.delete",
        tenant_id=tenant_id,
        actor_id=actor_id,
        job_id=job_id,
        metadata={"object_prefix": object_prefix},
    )
    return "deleted"


def cancel_job(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    job_store: Any,
    outbox: Any,
    audit_log: Any,
) -> str:
    job = _require_job(tenant_id=tenant_id, job_id=job_id, job_store=job_store)
    status = str(job.get("status") or "")

    if status in CANCEL_IDEMPOTENT_STATUSES:
        return status

    if status in CANCEL_IMMEDIATE_STATUSES:
        _set_status(job_store, tenant_id, job_id, "cancel_requested", progress=max(20, derive_progress(status=status, raw_progress=job.get("progress"))))
        _set_status(job_store, tenant_id, job_id, "canceled", progress=100)
        _prune_pending_outbox(outbox, tenant_id=tenant_id, job_id=job_id, error_code="job.canceled")
        _append_audit(audit_log, action="job.cancel", tenant_id=tenant_id, actor_id=actor_id, job_id=job_id)
        return "canceled"

    if status in CANCEL_REQUESTABLE_STATUSES:
        current_progress = derive_progress(status=status, raw_progress=job.get("progress"))
        _set_status(job_store, tenant_id, job_id, "cancel_requested", progress=max(20, current_progress))
        _append_audit(audit_log, action="job.cancel_requested", tenant_id=tenant_id, actor_id=actor_id, job_id=job_id)
        return "cancel_requested"

    raise JobLifecycleError(
        status_code=409,
        error_code="job.cancel.invalid_state",
        message="Job kann in diesem Status nicht abgebrochen werden.",
    )


def _append_audit(
    audit_log: Any,
    *,
    action: str,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "action": action,
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "job_id": job_id,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    }
    if metadata:
        payload.update(metadata)
    append = getattr(audit_log, "append", None)
    if callable(append):
        append(payload)


def _set_status(job_store: Any, tenant_id: str, job_id: str, status: str, *, progress: int | None) -> None:
    setter = getattr(job_store, "set_status", None)
    if setter is None:
        raise JobLifecycleError(status_code=503, error_code="job.lifecycle.unavailable", message="Job-Store fehlt.")
    try:
        setter(tenant_id, job_id, status, progress=progress)
    except TypeError:
        setter(tenant_id, job_id, status)


def _require_job(*, tenant_id: str, job_id: str, job_store: Any) -> dict[str, Any]:
    getter = getattr(job_store, "get", None)
    if getter is None:
        raise JobLifecycleError(status_code=503, error_code="job.lifecycle.unavailable", message="Job-Store fehlt.")
    row = getter(tenant_id, job_id)
    if row is None:
        raise JobLifecycleError(status_code=404, error_code="job.not_found", message="Job nicht gefunden.")
    return row


def _object_prefix_for_job(*, tenant_id: str, job_id: str, object_key: Any) -> str:
    raw = str(object_key or "").strip()
    expected_prefix = f"tenant/{tenant_id}/{job_id}/"
    if raw.startswith(expected_prefix):
        return expected_prefix
    return expected_prefix


def _prune_pending_outbox(outbox: Any, *, tenant_id: str, job_id: str, error_code: str) -> None:
    prune_pending = getattr(outbox, "prune_pending_for_job", None)
    if not callable(prune_pending):
        return
    try:
        prune_pending(tenant_id=tenant_id, job_id=job_id, error_code=error_code)
    except TypeError:
        prune_pending(tenant_id=tenant_id, job_id=job_id)


def _cleanup_job_internal_state(
    *,
    tenant_id: str,
    job_id: str,
    checkpoint_store: Any | None,
    artifact_store: Any | None,
    transcript_store: Any | None,
) -> None:
    for store in (checkpoint_store, artifact_store, transcript_store):
        if store is None:
            continue
        _delete_for_job(store, tenant_id=tenant_id, job_id=job_id)


def _extract_transcription_options(job: dict[str, Any]) -> dict[str, Any]:
    if isinstance(job.get("transcription_options"), dict):
        return safe_worker_decoding_options(job.get("transcription_options"))

    raw = job.get("transcription_options_json")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return safe_worker_decoding_options(parsed)

    return safe_worker_decoding_options(None)


def _delete_for_job(store: Any, *, tenant_id: str, job_id: str) -> None:
    delete = getattr(store, "delete", None)
    if not callable(delete):
        return
    try:
        delete(tenant_id=tenant_id, job_id=job_id)
    except TypeError:
        delete(tenant_id, job_id)
