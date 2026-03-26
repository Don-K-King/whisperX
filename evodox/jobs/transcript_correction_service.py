from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any
from uuid import uuid4

from evodox.jobs.transcript_service import (
    TranscriptConflictError,
    TranscriptValidationError,
    UpdateTranscriptResponse,
    get_transcript,
)

EPSILON = 1e-6
SEED_OVERLAP_SNAP_SECONDS = 0.05
DEFAULT_REVIEW_STATUS = "in_review"


@dataclass(frozen=True)
class TranscriptStatusResponse:
    job_id: str
    review_status: str
    is_final: bool
    final_set_by: str | None = None
    final_set_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class CorrectionSessionCreateInput:
    job_id: str
    base_version: int | None = None
    autosave_enabled: bool = False
    force_reseed_from_transcript: bool = False


@dataclass(frozen=True)
class CorrectionSessionOptionsInput:
    job_id: str
    session_id: str
    autosave_enabled: bool


@dataclass(frozen=True)
class CorrectionSessionApplyInput:
    job_id: str
    session_id: str
    operations: list[dict[str, Any]]
    autosave_enabled: bool | None = None


@dataclass(frozen=True)
class CorrectionSessionCommitInput:
    job_id: str
    session_id: str
    base_version: int
    edit_reason: str


@dataclass(frozen=True)
class TranscriptStatusUpdateInput:
    job_id: str
    review_status: str | None = None
    is_final: bool | None = None


@dataclass(frozen=True)
class CorrectionSessionResponse:
    session_id: str
    job_id: str
    base_version: int
    working_version: int
    autosave_enabled: bool
    history_index: int
    segments: list[dict[str, Any]]
    speaker_labels: dict[str, str]
    operation_log: list[dict[str, Any]]
    review_status: str
    is_final: bool


class InMemoryTranscriptCorrectionStore:
    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self._status: dict[tuple[str, str], dict[str, Any]] = {}

    def create_session(self, *, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        key = (tenant_id, str(payload["session_id"]))
        self._sessions[key] = _clone_session(payload)
        return _clone_session(self._sessions[key])

    def get_session(self, *, tenant_id: str, session_id: str) -> dict[str, Any] | None:
        payload = self._sessions.get((tenant_id, session_id))
        return None if payload is None else _clone_session(payload)

    def update_session(self, *, tenant_id: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._sessions[(tenant_id, session_id)] = _clone_session(payload)
        return _clone_session(self._sessions[(tenant_id, session_id)])

    def delete_session(self, *, tenant_id: str, session_id: str) -> None:
        self._sessions.pop((tenant_id, session_id), None)

    def get_status(self, *, tenant_id: str, job_id: str) -> dict[str, Any]:
        status = self._status.get((tenant_id, job_id))
        if status is None:
            return {
                "review_status": DEFAULT_REVIEW_STATUS,
                "is_final": False,
                "final_set_by": None,
                "final_set_at": None,
                "updated_at": None,
            }
        return dict(status)

    def set_status(
        self,
        *,
        tenant_id: str,
        job_id: str,
        review_status: str | None,
        is_final: bool | None,
        actor_id: str,
    ) -> dict[str, Any]:
        current = self.get_status(tenant_id=tenant_id, job_id=job_id)
        now = datetime.now(tz=timezone.utc).isoformat()
        next_status = {
            "review_status": current["review_status"] if review_status is None else review_status,
            "is_final": current["is_final"] if is_final is None else bool(is_final),
            "final_set_by": current.get("final_set_by"),
            "final_set_at": current.get("final_set_at"),
            "updated_at": now,
        }
        if is_final is True:
            next_status["final_set_by"] = actor_id
            next_status["final_set_at"] = now
        if is_final is False:
            next_status["final_set_by"] = None
            next_status["final_set_at"] = None
        self._status[(tenant_id, job_id)] = next_status
        return dict(next_status)


def create_correction_session(
    request: CorrectionSessionCreateInput,
    *,
    tenant_id: str,
    actor_id: str,
    transcript_repo: Any,
    correction_store: Any,
    audit_log: Any,
) -> CorrectionSessionResponse:
    _require_store(correction_store)
    transcript = get_transcript(tenant_id=tenant_id, job_id=request.job_id, transcript_repo=transcript_repo)
    base_version = transcript.version if request.base_version is None else int(request.base_version)
    if base_version != transcript.version:
        raise TranscriptConflictError()
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=request.job_id)
    seed_segments = _normalize_segments(transcript.segments, snap_small_overlaps=True)
    now = datetime.now(tz=timezone.utc).isoformat()
    payload = {
        "session_id": f"cs_{uuid4().hex[:16]}",
        "job_id": request.job_id,
        "actor_id": actor_id,
        "base_version": base_version,
        "autosave_enabled": bool(request.autosave_enabled),
        "speaker_labels": dict(transcript.speaker_labels),
        "review_status": status["review_status"],
        "is_final": bool(status["is_final"]),
        "history_index": 0,
        "history": [{"segments": _clone_segments(seed_segments), "summary": None, "ts": now}],
        "updated_at": now,
        "created_at": now,
    }
    created = correction_store.create_session(tenant_id=tenant_id, payload=payload)
    if bool(request.force_reseed_from_transcript) and str(created.get("session_id", "")) != str(payload["session_id"]):
        now = datetime.now(tz=timezone.utc).isoformat()
        reseeded = _reseed_session_payload(
            session=created,
            actor_id=actor_id,
            base_version=base_version,
            autosave_enabled=bool(request.autosave_enabled),
            speaker_labels=dict(transcript.speaker_labels),
            review_status=status["review_status"],
            is_final=bool(status["is_final"]),
            seed_segments=seed_segments,
            now_iso=now,
        )
        created = correction_store.update_session(tenant_id=tenant_id, session_id=str(created["session_id"]), payload=reseeded)
        _audit_append(
            audit_log,
            {
                "action": "transcript.correction_session.reseeded_from_transcript",
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "job_id": request.job_id,
                "session_id": created["session_id"],
                "base_version": base_version,
                "autosave_enabled": bool(request.autosave_enabled),
                "ts": now,
            },
        )
    _audit_append(
        audit_log,
        {
            "action": "transcript.correction_session.created",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "session_id": created["session_id"],
            "base_version": base_version,
            "autosave_enabled": bool(request.autosave_enabled),
            "ts": now,
        },
    )
    return _map_session(created, status=status)


def get_correction_session(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    session_id: str,
    correction_store: Any,
) -> CorrectionSessionResponse:
    session = _require_session(correction_store, tenant_id=tenant_id, job_id=job_id, session_id=session_id)
    _assert_actor(session, actor_id)
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=job_id)
    return _map_session(session, status=status)


def set_correction_session_options(
    request: CorrectionSessionOptionsInput,
    *,
    tenant_id: str,
    actor_id: str,
    correction_store: Any,
    audit_log: Any,
) -> CorrectionSessionResponse:
    session = _require_session(correction_store, tenant_id=tenant_id, job_id=request.job_id, session_id=request.session_id)
    _assert_actor(session, actor_id)
    session["autosave_enabled"] = bool(request.autosave_enabled)
    session["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    correction_store.update_session(tenant_id=tenant_id, session_id=request.session_id, payload=session)
    _audit_append(
        audit_log,
        {
            "action": "transcript.correction_session.updated",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "session_id": request.session_id,
            "autosave_enabled": bool(request.autosave_enabled),
            "ts": session["updated_at"],
        },
    )
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=request.job_id)
    return _map_session(session, status=status)


def apply_correction_operations(
    request: CorrectionSessionApplyInput,
    *,
    tenant_id: str,
    actor_id: str,
    correction_store: Any,
    audit_log: Any,
) -> CorrectionSessionResponse:
    if not isinstance(request.operations, list) or len(request.operations) == 0:
        raise TranscriptValidationError("transcript.invalid_operations", "Mindestens eine Operation ist erforderlich.")
    session = _require_session(correction_store, tenant_id=tenant_id, job_id=request.job_id, session_id=request.session_id)
    _assert_actor(session, actor_id)
    current_segments = _session_segments(session)
    updated_segments = _clone_segments(current_segments)
    summaries: list[dict[str, Any]] = []
    for operation in request.operations:
        updated_segments, summary = _apply_operation(updated_segments, operation)
        summaries.append(summary)
    _validate_segments(updated_segments)

    history = _clone_history(session.get("history", []))
    index = max(0, int(session.get("history_index", len(history) - 1)))
    if index < len(history) - 1:
        history = history[: index + 1]
    now = datetime.now(tz=timezone.utc).isoformat()
    history.append({"segments": _clone_segments(updated_segments), "summary": {"operations": summaries}, "ts": now})
    session["history"] = history
    session["history_index"] = len(history) - 1
    if request.autosave_enabled is not None:
        session["autosave_enabled"] = bool(request.autosave_enabled)
    session["updated_at"] = now
    correction_store.update_session(tenant_id=tenant_id, session_id=request.session_id, payload=session)
    _audit_append(
        audit_log,
        {
            "action": "transcript.correction_session.operations_applied",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "session_id": request.session_id,
            "operations_count": len(summaries),
            "history_index": int(session["history_index"]),
            "ts": now,
        },
    )
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=request.job_id)
    return _map_session(session, status=status)

def undo_correction_session(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    session_id: str,
    correction_store: Any,
    audit_log: Any,
) -> CorrectionSessionResponse:
    session = _require_session(correction_store, tenant_id=tenant_id, job_id=job_id, session_id=session_id)
    _assert_actor(session, actor_id)
    index = max(0, int(session.get("history_index", 0)))
    if index > 0:
        session["history_index"] = index - 1
    session["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    correction_store.update_session(tenant_id=tenant_id, session_id=session_id, payload=session)
    _audit_append(
        audit_log,
        {
            "action": "transcript.correction_session.undo",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": job_id,
            "session_id": session_id,
            "history_index": int(session["history_index"]),
            "ts": session["updated_at"],
        },
    )
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=job_id)
    return _map_session(session, status=status)


def redo_correction_session(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    session_id: str,
    correction_store: Any,
    audit_log: Any,
) -> CorrectionSessionResponse:
    session = _require_session(correction_store, tenant_id=tenant_id, job_id=job_id, session_id=session_id)
    _assert_actor(session, actor_id)
    history = _clone_history(session.get("history", []))
    index = max(0, int(session.get("history_index", 0)))
    if index < len(history) - 1:
        session["history_index"] = index + 1
    session["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    correction_store.update_session(tenant_id=tenant_id, session_id=session_id, payload=session)
    _audit_append(
        audit_log,
        {
            "action": "transcript.correction_session.redo",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": job_id,
            "session_id": session_id,
            "history_index": int(session["history_index"]),
            "ts": session["updated_at"],
        },
    )
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=job_id)
    return _map_session(session, status=status)


def discard_correction_session(
    *,
    tenant_id: str,
    actor_id: str,
    job_id: str,
    session_id: str,
    correction_store: Any,
    audit_log: Any,
) -> CorrectionSessionResponse:
    session = _require_session(correction_store, tenant_id=tenant_id, job_id=job_id, session_id=session_id)
    _assert_actor(session, actor_id)
    history = _clone_history(session.get("history", []))
    if len(history) == 0:
        raise TranscriptValidationError("transcript.correction_invalid_session", "Korrektursitzung ist ungueltig.")
    session["history"] = [history[0]]
    session["history_index"] = 0
    session["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    correction_store.update_session(tenant_id=tenant_id, session_id=session_id, payload=session)
    _audit_append(
        audit_log,
        {
            "action": "transcript.correction_session.discarded",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": job_id,
            "session_id": session_id,
            "ts": session["updated_at"],
        },
    )
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=job_id)
    return _map_session(session, status=status)


def commit_correction_session(
    request: CorrectionSessionCommitInput,
    *,
    tenant_id: str,
    actor_id: str,
    transcript_repo: Any,
    correction_store: Any,
    audit_log: Any,
) -> UpdateTranscriptResponse:
    if not isinstance(request.base_version, int) or request.base_version < 1:
        raise TranscriptValidationError("transcript.invalid_base_version", "base_version ist ungueltig.")
    if not isinstance(request.edit_reason, str) or len(request.edit_reason.strip()) < 3:
        raise TranscriptValidationError("transcript.invalid_edit_reason", "edit_reason ist erforderlich.")
    session = _require_session(correction_store, tenant_id=tenant_id, job_id=request.job_id, session_id=request.session_id)
    _assert_actor(session, actor_id)
    if int(session.get("base_version", 0)) != request.base_version:
        raise TranscriptConflictError()
    segments = _session_segments(session)
    _validate_segments(segments)
    kwargs = {
        "tenant_id": tenant_id,
        "job_id": request.job_id,
        "expected_base_version": request.base_version,
        "segments": segments,
        "speaker_labels": dict(session.get("speaker_labels", {})),
    }
    try:
        new_version = transcript_repo.save_new_version(
            **kwargs,
            created_by=actor_id,
            edit_reason=request.edit_reason.strip(),
            save_source="manual",
        )
    except TypeError:
        new_version = transcript_repo.save_new_version(**kwargs)
    now = datetime.now(tz=timezone.utc).isoformat()
    session["base_version"] = int(new_version)
    session["history"] = [{"segments": _clone_segments(segments), "summary": None, "ts": now}]
    session["history_index"] = 0
    session["updated_at"] = now
    correction_store.update_session(tenant_id=tenant_id, session_id=request.session_id, payload=session)
    _audit_append(
        audit_log,
        {
            "action": "transcript.correction_session.committed",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "session_id": request.session_id,
            "base_version": request.base_version,
            "new_version": int(new_version),
            "edit_reason": request.edit_reason,
            "ts": now,
        },
    )
    return UpdateTranscriptResponse(job_id=request.job_id, version=int(new_version), saved_at=now)


def get_transcript_status(*, tenant_id: str, job_id: str, correction_store: Any) -> TranscriptStatusResponse:
    status = _get_status(correction_store, tenant_id=tenant_id, job_id=job_id)
    return TranscriptStatusResponse(
        job_id=job_id,
        review_status=status["review_status"],
        is_final=bool(status["is_final"]),
        final_set_by=status.get("final_set_by"),
        final_set_at=status.get("final_set_at"),
        updated_at=status.get("updated_at"),
    )


def update_transcript_status(
    request: TranscriptStatusUpdateInput,
    *,
    tenant_id: str,
    actor_id: str,
    transcript_repo: Any,
    correction_store: Any,
    audit_log: Any,
) -> TranscriptStatusResponse:
    _require_store(correction_store)
    get_transcript(tenant_id=tenant_id, job_id=request.job_id, transcript_repo=transcript_repo)
    if request.review_status is None and request.is_final is None:
        raise TranscriptValidationError("transcript.invalid_status_update", "Es muss mindestens ein Statusfeld gesetzt werden.")
    if request.review_status is not None:
        review_status = str(request.review_status).strip()
        if len(review_status) < 2 or len(review_status) > 64:
            raise TranscriptValidationError("transcript.invalid_review_status", "review_status ist ungueltig.")
    else:
        review_status = None
    status = correction_store.set_status(
        tenant_id=tenant_id,
        job_id=request.job_id,
        review_status=review_status,
        is_final=request.is_final,
        actor_id=actor_id,
    )
    _audit_append(
        audit_log,
        {
            "action": "transcript.status.updated",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "review_status": status["review_status"],
            "is_final": bool(status["is_final"]),
            "ts": status.get("updated_at") or datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    return TranscriptStatusResponse(
        job_id=request.job_id,
        review_status=status["review_status"],
        is_final=bool(status["is_final"]),
        final_set_by=status.get("final_set_by"),
        final_set_at=status.get("final_set_at"),
        updated_at=status.get("updated_at"),
    )


def _require_store(store: Any) -> None:
    for method_name in ("create_session", "get_session", "update_session", "set_status", "get_status"):
        if not callable(getattr(store, method_name, None)):
            raise TranscriptValidationError("transcript.correction_unavailable", "Korrekturmodus ist nicht verfuegbar.")


def _require_session(store: Any, *, tenant_id: str, job_id: str, session_id: str) -> dict[str, Any]:
    _require_store(store)
    session = store.get_session(tenant_id=tenant_id, session_id=session_id)
    if session is None:
        raise TranscriptValidationError("transcript.correction_session_not_found", "Korrektursitzung nicht gefunden.")
    if str(session.get("job_id")) != str(job_id):
        raise TranscriptValidationError("transcript.correction_session_not_found", "Korrektursitzung nicht gefunden.")
    return _clone_session(session)


def _assert_actor(session: dict[str, Any], actor_id: str) -> None:
    owner = str(session.get("actor_id", "")).strip()
    if owner and owner != actor_id:
        raise TranscriptValidationError("transcript.correction_session_forbidden", "Korrektursitzung gehoert zu anderem Bearbeiter.")


def _map_session(session: dict[str, Any], *, status: dict[str, Any] | None = None) -> CorrectionSessionResponse:
    resolved_status = status or {
        "review_status": str(session.get("review_status", DEFAULT_REVIEW_STATUS)),
        "is_final": bool(session.get("is_final", False)),
    }
    return CorrectionSessionResponse(
        session_id=str(session["session_id"]),
        job_id=str(session["job_id"]),
        base_version=int(session.get("base_version", 1)),
        working_version=int(session.get("base_version", 1)) + int(session.get("history_index", 0)),
        autosave_enabled=bool(session.get("autosave_enabled", False)),
        history_index=int(session.get("history_index", 0)),
        segments=_session_segments(session),
        speaker_labels=dict(session.get("speaker_labels", {})),
        operation_log=_session_operation_log(session),
        review_status=str(resolved_status.get("review_status", DEFAULT_REVIEW_STATUS)),
        is_final=bool(resolved_status.get("is_final", False)),
    )


def _session_segments(session: dict[str, Any]) -> list[dict[str, Any]]:
    history = _clone_history(session.get("history", []))
    if len(history) == 0:
        raise TranscriptValidationError("transcript.correction_invalid_session", "Korrektursitzung ist ungueltig.")
    index = max(0, min(int(session.get("history_index", 0)), len(history) - 1))
    return _clone_segments(history[index].get("segments", []))


def _session_operation_log(session: dict[str, Any]) -> list[dict[str, Any]]:
    history = _clone_history(session.get("history", []))
    if len(history) == 0:
        return []
    index = max(0, min(int(session.get("history_index", 0)), len(history) - 1))
    log: list[dict[str, Any]] = []
    for item in history[1 : index + 1]:
        summary = item.get("summary")
        if isinstance(summary, dict):
            log.append(dict(summary))
    return log


def _normalize_segments(
    raw_segments: list[dict[str, Any]],
    *,
    snap_small_overlaps: bool = False,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    previous_end = 0.0
    for idx, raw in enumerate(raw_segments):
        if not isinstance(raw, dict):
            raise TranscriptValidationError("transcript.invalid_segments", "segments enthaelt ungueltige Eintraege.")
        segment_id = str(raw.get("segment_id", "")).strip() or f"seg_{idx + 1:06d}"
        speaker = str(raw.get("speaker", "UNKNOWN")).strip() or "UNKNOWN"
        text = str(raw.get("text", ""))
        if _has_disallowed_control_chars(text) or _has_disallowed_control_chars(speaker):
            raise TranscriptValidationError("transcript.invalid_segments", "segments enthaelt ungueltige Zeichen.")
        has_start = "start" in raw
        has_end = "end" in raw
        try:
            start = float(raw.get("start", previous_end if has_end else previous_end))
            end = float(raw.get("end", start))
        except (TypeError, ValueError):
            raise TranscriptValidationError("transcript.invalid_segments", "start/end sind ungueltig.")
        if not has_start and not has_end:
            start = previous_end
            end = previous_end
        normalized.append(
            {
                "segment_id": segment_id,
                "speaker": speaker,
                "text": text,
                "start": start,
                "end": end,
            }
        )
        previous_end = end
    if snap_small_overlaps:
        normalized = _snap_small_overlaps(normalized, tolerance=SEED_OVERLAP_SNAP_SECONDS)
    _validate_segments(normalized)
    return normalized


def _snap_small_overlaps(segments: list[dict[str, Any]], *, tolerance: float) -> list[dict[str, Any]]:
    if len(segments) == 0:
        return []
    snapped: list[dict[str, Any]] = []
    previous_end: float | None = None
    for segment in segments:
        current = dict(segment)
        start = float(current.get("start", 0.0))
        end = float(current.get("end", 0.0))
        if previous_end is not None and start < previous_end:
            overlap = previous_end - start
            if overlap <= tolerance + EPSILON:
                start = previous_end
                if end < start:
                    end = start
                current["start"] = float(start)
                current["end"] = float(end)
        snapped.append(current)
        previous_end = float(current.get("end", end))
    return snapped


def _validate_segments(segments: list[dict[str, Any]]) -> None:
    if len(segments) == 0:
        raise TranscriptValidationError("transcript.invalid_segments", "segments duerfen nicht leer sein.")
    seen: set[str] = set()
    previous_end: float | None = None
    for segment in segments:
        segment_id = str(segment.get("segment_id", "")).strip()
        if len(segment_id) == 0 or segment_id in seen:
            raise TranscriptValidationError("transcript.invalid_segments", "segment_id ist ungueltig.")
        seen.add(segment_id)
        text = str(segment.get("text", ""))
        if len(text.strip()) == 0:
            raise TranscriptValidationError("transcript.invalid_segment_text", "segment text darf nicht leer sein.")
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))
        if not math.isfinite(start) or not math.isfinite(end):
            raise TranscriptValidationError("transcript.invalid_timeline", "Timeline ist ungueltig.")
        if start < 0.0 or end < 0.0 or start > end:
            raise TranscriptValidationError("transcript.invalid_timeline", "Timeline ist ungueltig.")
        if previous_end is not None:
            if start < previous_end - EPSILON:
                raise TranscriptValidationError("transcript.timeline_overlap", "Timeline enthaelt Ueberschneidungen.")
        previous_end = end


def _apply_operation(segments: list[dict[str, Any]], operation: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    op_type = str(operation.get("type", "")).strip().lower()
    if op_type == "set_segments":
        raw = operation.get("segments")
        if not isinstance(raw, list) or len(raw) == 0:
            raise TranscriptValidationError("transcript.invalid_operations", "set_segments erfordert segments.")
        normalized = _normalize_segments(raw)
        return normalized, {"type": "set_segments", "segments_count": len(normalized)}
    if op_type == "replace_literal":
        query = str(operation.get("query", ""))
        replace = str(operation.get("replace", ""))
        speaker = operation.get("speaker")
        replace_all = bool(operation.get("replace_all", True))
        if len(query) == 0 or len(query) > 255:
            raise TranscriptValidationError("transcript.invalid_operations", "replace_literal query ist ungueltig.")
        updated = _clone_segments(segments)
        replacements = 0
        for segment in updated:
            if speaker is not None and str(segment.get("speaker")) != str(speaker):
                continue
            text = str(segment.get("text", ""))
            if query not in text:
                continue
            if replace_all:
                count = text.count(query)
                segment["text"] = text.replace(query, replace)
                replacements += count
            else:
                segment["text"] = text.replace(query, replace, 1)
                replacements += 1
                break
        if replacements == 0:
            raise TranscriptValidationError("transcript.replace_no_match", "Keine passenden Treffer fuer replace_literal gefunden.")
        return updated, {"type": "replace_literal", "replacements": replacements}
    if op_type == "reassign_speaker":
        segment_id = str(operation.get("segment_id", "")).strip()
        speaker = str(operation.get("speaker", "")).strip()
        if len(segment_id) == 0 or len(speaker) == 0:
            raise TranscriptValidationError("transcript.invalid_operations", "reassign_speaker ist ungueltig.")
        updated = _clone_segments(segments)
        index = _find_index(updated, segment_id)
        if index < 0:
            raise TranscriptValidationError("transcript.invalid_operations", "segment_id wurde nicht gefunden.")
        target = dict(updated[index])
        start_char = operation.get("start_char")
        end_char = operation.get("end_char")
        if start_char is None or end_char is None:
            target["speaker"] = speaker
            updated[index] = target
            return updated, {"type": "reassign_speaker", "mode": "segment"}
        try:
            start_idx = int(start_char)
            end_idx = int(end_char)
        except (TypeError, ValueError):
            raise TranscriptValidationError("transcript.invalid_operations", "start_char/end_char sind ungueltig.")
        text = str(target.get("text", ""))
        if start_idx < 0 or end_idx <= start_idx or end_idx > len(text):
            raise TranscriptValidationError("transcript.invalid_operations", "start_char/end_char sind ausserhalb des Texts.")
        split = _split_segment(target, start_idx=start_idx, end_idx=end_idx, new_speaker=speaker)
        updated = updated[:index] + split + updated[index + 1 :]
        return updated, {"type": "reassign_speaker", "mode": "partial", "created_segments": len(split)}
    raise TranscriptValidationError("transcript.invalid_operations", "Operationstyp wird nicht unterstuetzt.")


def _split_segment(segment: dict[str, Any], *, start_idx: int, end_idx: int, new_speaker: str) -> list[dict[str, Any]]:
    text = str(segment.get("text", ""))
    left = text[:start_idx]
    middle = text[start_idx:end_idx]
    right = text[end_idx:]
    segment_id = str(segment.get("segment_id", f"seg_{uuid4().hex[:8]}"))
    old_speaker = str(segment.get("speaker", "UNKNOWN"))
    start = float(segment.get("start", 0.0))
    end = float(segment.get("end", start))
    duration = max(0.0, end - start)

    parts: list[tuple[str, str, str]] = []
    if len(left) > 0:
        parts.append((f"{segment_id}_a", old_speaker, left))
    parts.append((f"{segment_id}_b", new_speaker, middle))
    if len(right) > 0:
        parts.append((f"{segment_id}_c", old_speaker, right))

    total_chars = max(1, sum(len(part[2]) for part in parts))
    cursor = start
    created: list[dict[str, Any]] = []
    for idx, (part_id, part_speaker, part_text) in enumerate(parts):
        if duration <= EPSILON:
            part_start = start
            part_end = start
        else:
            part_start = cursor
            if idx == len(parts) - 1:
                part_end = end
            else:
                part_end = cursor + (duration * (float(len(part_text)) / float(total_chars)))
            cursor = part_end
        created.append(
            {
                "segment_id": part_id,
                "speaker": part_speaker,
                "text": part_text,
                "start": float(part_start),
                "end": float(part_end),
            }
        )
    return created


def _find_index(segments: list[dict[str, Any]], segment_id: str) -> int:
    for index, segment in enumerate(segments):
        if str(segment.get("segment_id", "")) == segment_id:
            return index
    return -1


def _get_status(store: Any, *, tenant_id: str, job_id: str) -> dict[str, Any]:
    if not callable(getattr(store, "get_status", None)):
        return {
            "review_status": DEFAULT_REVIEW_STATUS,
            "is_final": False,
            "final_set_by": None,
            "final_set_at": None,
            "updated_at": None,
        }
    payload = store.get_status(tenant_id=tenant_id, job_id=job_id)
    if not isinstance(payload, dict):
        return {
            "review_status": DEFAULT_REVIEW_STATUS,
            "is_final": False,
            "final_set_by": None,
            "final_set_at": None,
            "updated_at": None,
        }
    return {
        "review_status": str(payload.get("review_status", DEFAULT_REVIEW_STATUS)),
        "is_final": bool(payload.get("is_final", False)),
        "final_set_by": payload.get("final_set_by"),
        "final_set_at": payload.get("final_set_at"),
        "updated_at": payload.get("updated_at"),
    }


def _clone_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(segment) for segment in segments]


def _clone_history(history: Any) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        return []
    cloned: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        cloned.append(
            {
                "segments": _clone_segments(item.get("segments", [])),
                "summary": dict(item["summary"]) if isinstance(item.get("summary"), dict) else None,
                "ts": item.get("ts"),
            }
        )
    return cloned


def _clone_session(session: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(session)
    cloned["speaker_labels"] = dict(session.get("speaker_labels", {}))
    cloned["history"] = _clone_history(session.get("history", []))
    return cloned


def _has_disallowed_control_chars(value: str) -> bool:
    return any(ord(char) < 32 and char not in {"\n", "\r", "\t"} for char in value)


def _reseed_session_payload(
    *,
    session: dict[str, Any],
    actor_id: str,
    base_version: int,
    autosave_enabled: bool,
    speaker_labels: dict[str, str],
    review_status: str,
    is_final: bool,
    seed_segments: list[dict[str, Any]],
    now_iso: str,
) -> dict[str, Any]:
    updated = _clone_session(session)
    updated["actor_id"] = actor_id
    updated["base_version"] = int(base_version)
    updated["autosave_enabled"] = bool(autosave_enabled)
    updated["speaker_labels"] = dict(speaker_labels)
    updated["review_status"] = str(review_status)
    updated["is_final"] = bool(is_final)
    updated["history_index"] = 0
    updated["history"] = [{"segments": _clone_segments(seed_segments), "summary": None, "ts": now_iso}]
    updated["updated_at"] = now_iso
    return updated


def _audit_append(audit_log: Any, payload: dict[str, Any]) -> None:
    if hasattr(audit_log, "append"):
        audit_log.append(payload)
        return
    if isinstance(audit_log, list):
        audit_log.append(payload)
