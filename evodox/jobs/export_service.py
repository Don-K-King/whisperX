from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
from typing import Any

ALLOWED_FORMATS = frozenset({"txt", "json", "srt", "vtt"})


@dataclass(frozen=True)
class ExportRequestInput:
    job_id: str
    transcript_version: int
    format: str
    idempotency_key: str


@dataclass(frozen=True)
class ExportQueuedResponse:
    export_id: str
    status: str


class ExportValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class InMemoryTranscriptReadRepository:
    def __init__(self, data: dict[tuple[str, str, int], dict[str, Any]]) -> None:
        self._data = dict(data)

    def get_version(self, tenant_id: str, job_id: str, version: int) -> dict[str, Any] | None:
        item = self._data.get((tenant_id, job_id, version))
        return None if item is None else dict(item)


class InMemoryExportArtifactStore:
    def __init__(self) -> None:
        self._by_id: dict[tuple[str, str], dict[str, Any]] = {}

    def put(self, *, tenant_id: str, export_id: str, payload: dict[str, Any]) -> None:
        self._by_id[(tenant_id, export_id)] = dict(payload)

    def get(self, tenant_id: str, export_id: str) -> dict[str, Any] | None:
        item = self._by_id.get((tenant_id, export_id))
        return None if item is None else dict(item)


def queue_export(
    request: ExportRequestInput,
    *,
    tenant_id: str,
    actor_id: str,
    transcript_repo: Any,
    export_store: Any,
    audit_log: Any,
) -> ExportQueuedResponse:
    _validate_request(request)
    transcript = transcript_repo.get_version(tenant_id, request.job_id, request.transcript_version)
    if transcript is None:
        raise ExportValidationError("export.transcript_not_found", "Transcript-Version wurde nicht gefunden.")

    segments = list(transcript.get("segments", []))
    speaker_labels = transcript.get("speaker_labels", {})
    segments_with_labels = _apply_speaker_labels(segments=segments, speaker_labels=speaker_labels)
    render_segments = segments_with_labels if request.format == "json" else segments
    content = _render_export(fmt=request.format, segments=render_segments)
    export_id = f"exp_{tenant_id}_{request.job_id}_{request.transcript_version}_{request.format}"
    export_store.put(
        tenant_id=tenant_id,
        export_id=export_id,
        payload={
            "job_id": request.job_id,
            "format": request.format,
            "transcript_version": request.transcript_version,
            "content": content,
            "status": "queued",
        },
    )
    ts = datetime.now(tz=timezone.utc).isoformat()
    _audit_append(
        audit_log,
        {
            "action": "export.requested",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "job_id": request.job_id,
            "export_id": export_id,
            "format": request.format,
            "transcript_version": request.transcript_version,
            "ts": ts,
        },
    )
    return ExportQueuedResponse(export_id=export_id, status="queued")


def _validate_request(request: ExportRequestInput) -> None:
    if request.format not in ALLOWED_FORMATS:
        raise ExportValidationError("export.invalid_format", "format muss txt|json|srt|vtt sein.")
    if not isinstance(request.transcript_version, int) or request.transcript_version < 1:
        raise ExportValidationError("export.invalid_version", "transcript_version ist ungültig.")
    if not isinstance(request.idempotency_key, str) or len(request.idempotency_key.strip()) < 8:
        raise ExportValidationError("export.invalid_idempotency_key", "Idempotency-Key ist ungültig.")


def _render_export(*, fmt: str, segments: list[dict[str, Any]]) -> str:
    if fmt == "json":
        import json

        return json.dumps({"segments": segments}, ensure_ascii=False, sort_keys=True)
    if fmt == "txt":
        return "\n".join(_safe_text(s.get("text", "")) for s in segments)
    if fmt == "srt":
        lines = []
        for idx, seg in enumerate(segments, start=1):
            lines.extend(
                [
                    str(idx),
                    f"{_srt_ts(float(seg.get('start', 0.0)))} --> {_srt_ts(float(seg.get('end', 0.0)))}",
                    _safe_text(seg.get("text", "")),
                    "",
                ]
            )
        return "\n".join(lines)
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{_vtt_ts(float(seg.get('start', 0.0)))} --> {_vtt_ts(float(seg.get('end', 0.0)))}")
        lines.append(_safe_text(seg.get("text", "")))
        lines.append("")
    return "\n".join(lines)


def _apply_speaker_labels(*, segments: list[dict[str, Any]], speaker_labels: Any) -> list[dict[str, Any]]:
    labels = speaker_labels if isinstance(speaker_labels, dict) else {}
    applied: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        speaker_key = str(segment.get("speaker", "UNKNOWN"))
        alias = labels.get(speaker_key)
        speaker_name = str(alias).strip() if alias is not None else speaker_key
        normalized = dict(segment)
        normalized["speaker"] = speaker_name if speaker_name else speaker_key
        applied.append(normalized)
    return applied


def _safe_text(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _srt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _vtt_ts(seconds: float) -> str:
    return _srt_ts(seconds).replace(",", ".")


def _audit_append(audit_log: Any, payload: dict[str, Any]) -> None:
    if hasattr(audit_log, "append"):
        audit_log.append(payload)
        return
    if isinstance(audit_log, list):
        audit_log.append(payload)
