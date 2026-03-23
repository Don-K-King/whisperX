from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class TranscriptResponse:
    job_id: str
    version: int
    segments: list[dict[str, Any]]
    speaker_labels: dict[str, str]


@dataclass(frozen=True)
class UpdateTranscriptInput:
    job_id: str
    base_version: int
    segments: list[dict[str, Any]]
    edit_reason: str


@dataclass(frozen=True)
class UpdateTranscriptSpeakerLabelsInput:
    job_id: str
    base_version: int
    speaker_labels: dict[str, str]
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
        self._versions: dict[tuple[str, str, int], dict[str, Any]] = {}

    def seed(
        self,
        *,
        tenant_id: str,
        job_id: str,
        version: int,
        segments: list[dict[str, Any]],
        speaker_labels: dict[str, str] | None = None,
    ) -> None:
        self._by_job[(tenant_id, job_id)] = {"version": version}
        self._versions[(tenant_id, job_id, version)] = {
            "segments": [dict(s) for s in segments],
            "speaker_labels": dict(speaker_labels or {}),
        }

    def get_current(self, tenant_id: str, job_id: str) -> TranscriptResponse | None:
        state = self._by_job.get((tenant_id, job_id))
        if state is None:
            return None
        version = int(state["version"])
        version_payload = self._versions.get((tenant_id, job_id, version), {})
        segments = [dict(s) for s in version_payload.get("segments", [])]
        speaker_labels = dict(version_payload.get("speaker_labels", {}))
        return TranscriptResponse(
            job_id=job_id,
            version=version,
            segments=segments,
            speaker_labels=speaker_labels,
        )

    def get_version(self, tenant_id: str, job_id: str, version: int) -> dict[str, Any] | None:
        payload = self._versions.get((tenant_id, job_id, int(version)))
        if payload is None:
            return None
        return {
            "segments": [dict(s) for s in payload.get("segments", [])],
            "speaker_labels": dict(payload.get("speaker_labels", {})),
        }

    def save_new_version(
        self,
        *,
        tenant_id: str,
        job_id: str,
        expected_base_version: int,
        segments: list[dict[str, Any]],
        speaker_labels: dict[str, str] | None = None,
    ) -> int:
        state = self._by_job.get((tenant_id, job_id))
        if state is None:
            raise TranscriptValidationError("transcript.not_found", "Transcript wurde nicht gefunden.")
        current_version = int(state["version"])
        if current_version != expected_base_version:
            raise TranscriptConflictError()
        current_payload = self._versions.get((tenant_id, job_id, current_version), {})
        new_version = current_version + 1
        state["version"] = new_version
        self._versions[(tenant_id, job_id, new_version)] = {
            "segments": [dict(s) for s in segments],
            "speaker_labels": dict(current_payload.get("speaker_labels", {}))
            if speaker_labels is None
            else dict(speaker_labels),
        }
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


def update_transcript_speaker_labels(
    request: UpdateTranscriptSpeakerLabelsInput,
    *,
    tenant_id: str,
    actor_id: str,
    transcript_repo: Any,
    audit_log: Any,
) -> UpdateTranscriptResponse:
    _validate_speaker_labels_update(request)
    current = get_transcript(tenant_id=tenant_id, job_id=request.job_id, transcript_repo=transcript_repo)
    normalized_labels = _normalize_speaker_labels(request.speaker_labels)
    new_version = transcript_repo.save_new_version(
        tenant_id=tenant_id,
        job_id=request.job_id,
        expected_base_version=request.base_version,
        segments=current.segments,
        speaker_labels=normalized_labels,
    )
    saved_at = datetime.now(tz=timezone.utc).isoformat()
    _audit_append(
        audit_log,
        {
            "action": "transcript.speaker_labels.updated",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "base_version": request.base_version,
            "new_version": new_version,
            "speaker_labels_count": len(normalized_labels),
            "edit_reason": request.edit_reason,
            "ts": saved_at,
        },
    )
    return UpdateTranscriptResponse(job_id=request.job_id, version=new_version, saved_at=saved_at)


def _validate_update(request: UpdateTranscriptInput) -> None:
    if not isinstance(request.base_version, int) or request.base_version < 1:
        raise TranscriptValidationError("transcript.invalid_base_version", "base_version ist ungueltig.")
    if not isinstance(request.segments, list) or len(request.segments) == 0:
        raise TranscriptValidationError("transcript.invalid_segments", "segments duerfen nicht leer sein.")
    if not isinstance(request.edit_reason, str) or len(request.edit_reason.strip()) < 3:
        raise TranscriptValidationError("transcript.invalid_edit_reason", "edit_reason ist erforderlich.")
    for segment in request.segments:
        text = str(segment.get("text", ""))
        if _has_disallowed_control_chars(text):
            raise TranscriptValidationError(
                "transcript.invalid_segment_text",
                "segment text enthaelt ungueltige Steuerzeichen.",
            )


def _validate_speaker_labels_update(request: UpdateTranscriptSpeakerLabelsInput) -> None:
    if not isinstance(request.base_version, int) or request.base_version < 1:
        raise TranscriptValidationError("transcript.invalid_base_version", "base_version ist ungueltig.")
    if not isinstance(request.speaker_labels, dict):
        raise TranscriptValidationError("transcript.invalid_speaker_labels", "speaker_labels ist ungueltig.")
    if not isinstance(request.edit_reason, str) or len(request.edit_reason.strip()) < 3:
        raise TranscriptValidationError("transcript.invalid_edit_reason", "edit_reason ist erforderlich.")
    for raw_key, raw_value in request.speaker_labels.items():
        key = str(raw_key).strip()
        value = str(raw_value).strip()
        if len(key) == 0 or len(key) > 32:
            raise TranscriptValidationError(
                "transcript.invalid_speaker_label_key",
                "speaker label key ist ungueltig.",
            )
        if len(value) > 80:
            raise TranscriptValidationError(
                "transcript.invalid_speaker_label_value",
                "speaker label value ist ungueltig.",
            )
        if _has_disallowed_control_chars(key) or _has_disallowed_control_chars(value):
            raise TranscriptValidationError(
                "transcript.invalid_speaker_label_value",
                "speaker label value enthaelt ungueltige Steuerzeichen.",
            )


def _normalize_speaker_labels(raw_labels: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_key, raw_value in raw_labels.items():
        key = str(raw_key).strip()
        value = str(raw_value).strip()
        if len(value) == 0:
            continue
        normalized[key] = value
    return normalized


def _has_disallowed_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 and ch not in {"\n", "\r", "\t"} for ch in value)


def _audit_append(audit_log: Any, payload: dict[str, Any]) -> None:
    if hasattr(audit_log, "append"):
        audit_log.append(payload)
        return
    if isinstance(audit_log, list):
        audit_log.append(payload)
