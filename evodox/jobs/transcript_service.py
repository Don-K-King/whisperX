from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class TranscriptResponse:
    job_id: str
    version: int
    segments: list[dict[str, Any]]


@dataclass(frozen=True)
class UpdateTranscriptInput:
    job_id: str
    base_version: int
    segments: list[dict[str, Any]]
    edit_reason: str


@dataclass(frozen=True)
class UpdateTranscriptResponse:
    job_id: str
    version: int
    saved_at: str


class TranscriptValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class TranscriptConflictError(Exception):
    def __init__(self, error_code: str = "transcript.version_conflict"):
        self.error_code = error_code
        super().__init__(error_code)


class InMemoryTranscriptRepository:
    def __init__(self) -> None:
        self._by_job: dict[tuple[str, str], dict[str, Any]] = {}
        self._versions: dict[tuple[str, str, int], list[dict[str, Any]]] = {}

    def seed(self, *, tenant_id: str, job_id: str, version: int, segments: list[dict[str, Any]]) -> None:
        self._by_job[(tenant_id, job_id)] = {"version": version}
        self._versions[(tenant_id, job_id, version)] = [dict(s) for s in segments]

    def get_current(self, tenant_id: str, job_id: str) -> TranscriptResponse | None:
        state = self._by_job.get((tenant_id, job_id))
        if state is None:
            return None
        version = int(state["version"])
        segments = [dict(s) for s in self._versions.get((tenant_id, job_id, version), [])]
        return TranscriptResponse(job_id=job_id, version=version, segments=segments)

    def save_new_version(
        self,
        *,
        tenant_id: str,
        job_id: str,
        expected_base_version: int,
        segments: list[dict[str, Any]],
    ) -> int:
        state = self._by_job.get((tenant_id, job_id))
        if state is None:
            raise TranscriptValidationError("transcript.not_found", "Transcript wurde nicht gefunden.")
        current_version = int(state["version"])
        if current_version != expected_base_version:
            raise TranscriptConflictError()
        new_version = current_version + 1
        state["version"] = new_version
        self._versions[(tenant_id, job_id, new_version)] = [dict(s) for s in segments]
        return new_version


def get_transcript(*, tenant_id: str, job_id: str, transcript_repo: Any) -> TranscriptResponse:
    transcript = transcript_repo.get_current(tenant_id, job_id)
    if transcript is None:
        raise TranscriptValidationError("transcript.not_found", "Transcript wurde nicht gefunden.")
    return transcript


def update_transcript(
    request: UpdateTranscriptInput,
    *,
    tenant_id: str,
    actor_id: str,
    transcript_repo: Any,
    audit_log: Any,
) -> UpdateTranscriptResponse:
    _validate_update(request)
    new_version = transcript_repo.save_new_version(
        tenant_id=tenant_id,
        job_id=request.job_id,
        expected_base_version=request.base_version,
        segments=request.segments,
    )
    saved_at = datetime.now(tz=timezone.utc).isoformat()
    _audit_append(
        audit_log,
        {
            "action": "transcript.version.created",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "base_version": request.base_version,
            "new_version": new_version,
            "edit_reason": request.edit_reason,
            "ts": saved_at,
        },
    )
    return UpdateTranscriptResponse(job_id=request.job_id, version=new_version, saved_at=saved_at)


def _validate_update(request: UpdateTranscriptInput) -> None:
    if not isinstance(request.base_version, int) or request.base_version < 1:
        raise TranscriptValidationError("transcript.invalid_base_version", "base_version ist ungültig.")
    if not isinstance(request.segments, list) or len(request.segments) == 0:
        raise TranscriptValidationError("transcript.invalid_segments", "segments dürfen nicht leer sein.")
    if not isinstance(request.edit_reason, str) or len(request.edit_reason.strip()) < 3:
        raise TranscriptValidationError("transcript.invalid_edit_reason", "edit_reason ist erforderlich.")
    for segment in request.segments:
        text = str(segment.get("text", ""))
        if any(ord(ch) < 32 and ch not in {"\n", "\r", "\t"} for ch in text):
            raise TranscriptValidationError("transcript.invalid_segment_text", "segment text enthält ungültige Steuerzeichen.")


def _audit_append(audit_log: Any, payload: dict[str, Any]) -> None:
    if hasattr(audit_log, "append"):
        audit_log.append(payload)
        return
    if isinstance(audit_log, list):
        audit_log.append(payload)
