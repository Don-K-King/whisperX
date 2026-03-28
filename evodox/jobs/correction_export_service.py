from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import re
from typing import Any
from xml.sax.saxutils import escape as xml_escape
import zipfile


ALLOWED_CORRECTION_EXPORT_FORMATS = frozenset({"txt", "docx"})
ALLOWED_CORRECTION_EXPORT_PROFILES = frozenset({"court_transcript"})


@dataclass(frozen=True)
class CorrectionExportArtifact:
    content: bytes
    content_type: str
    filename: str


class CorrectionExportValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


def build_correction_court_export_artifact(
    *,
    job_id: str,
    session_id: str,
    base_version: int | None,
    working_version: int | None,
    review_status: str,
    is_final: bool,
    segments: list[dict[str, Any]],
    speaker_labels: dict[str, str] | None,
    fmt: str,
    profile: str,
    mode: str,
    created_at: datetime | None = None,
) -> CorrectionExportArtifact:
    normalized_format = _normalize_export_format(fmt)
    _normalize_export_profile(profile)
    normalized_mode = _normalize_export_mode(mode)

    created = created_at or datetime.now(tz=timezone.utc)
    render_segments = _build_render_segments(segments=segments, mode=normalized_mode)
    text = build_court_transcript_plain_text(
        job_id=job_id,
        session_id=session_id,
        base_version=base_version,
        working_version=working_version,
        review_status=review_status,
        is_final=is_final,
        segments=render_segments,
        speaker_labels=speaker_labels or {},
        created_at=created,
    )

    filename = build_court_export_filename(
        job_id=job_id,
        created_at=created,
        ext=normalized_format,
    )
    if normalized_format == "txt":
        return CorrectionExportArtifact(
            content=text.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
            filename=filename,
        )
    return CorrectionExportArtifact(
        content=build_docx_from_plain_text(text),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


def build_court_transcript_plain_text(
    *,
    job_id: str,
    session_id: str,
    base_version: int | None,
    working_version: int | None,
    review_status: str,
    is_final: bool,
    segments: list[dict[str, Any]],
    speaker_labels: dict[str, str],
    created_at: datetime,
) -> str:
    created_at_iso = created_at.astimezone(timezone.utc).isoformat()
    lines = [
        "Einvernahmeprotokoll",
        f"Job-ID: {_sanitize_inline(job_id)}",
        f"Session-ID: {_sanitize_inline(session_id)}",
        f"Basis-Version: {_format_version(base_version)}",
        f"Arbeits-Version: {_format_version(working_version)}",
        f"Review-Status: {_sanitize_inline(review_status)}",
        f"Final: {'Ja' if bool(is_final) else 'Nein'}",
        f"Exportzeitpunkt (UTC): {created_at_iso}",
        "------------------------------------------------------------",
        "",
    ]

    for segment in segments:
        speaker_key = str(segment.get("speaker", "UNKNOWN")).strip() or "UNKNOWN"
        speaker = _resolve_speaker_label(speaker_key=speaker_key, speaker_labels=speaker_labels)
        start = _format_timestamp(segment.get("start", 0))
        end = _format_timestamp(segment.get("end", 0))
        text = _sanitize_multiline(segment.get("text", ""))
        lines.append(f"[{start} - {end}] {speaker}:")
        lines.append(text)
        lines.append("")
    content = "\n".join(lines).rstrip()
    return f"{content}\n"


def build_court_export_filename(*, job_id: str, created_at: datetime, ext: str) -> str:
    safe_job = re.sub(r"[^a-zA-Z0-9_-]", "_", str(job_id or "job")).strip("_") or "job"
    safe_job = safe_job[:60]
    stamp = created_at.astimezone(timezone.utc).strftime("%Y%m%d_%H%M")
    safe_ext = "docx" if str(ext).lower() == "docx" else "txt"
    return f"einvernahmeprotokoll_{safe_job}_{stamp}.{safe_ext}"


def build_docx_from_plain_text(text: str) -> bytes:
    paragraphs = _build_docx_paragraphs(text)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 wp14">'
        f"<w:body>{paragraphs}<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\" />"
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0" />'
        '<w:cols w:space="708" /><w:docGrid w:linePitch="360" /></w:sectPr></w:body></w:document>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />'
        '<Default Extension="xml" ContentType="application/xml" />'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" />'
        "</Types>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml" />'
        "</Relationships>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _build_docx_paragraphs(text: str) -> str:
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraphs: list[str] = []
    for line in lines:
        escaped = xml_escape(_sanitize_multiline(line))
        if not escaped:
            paragraphs.append("<w:p />")
            continue
        paragraphs.append(f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>')
    return "".join(paragraphs)


def _build_render_segments(*, segments: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    normalized = _normalize_segments(segments)
    if mode == "raw" or len(normalized) < 2:
        return [dict(item) for item in normalized]

    compacted: list[dict[str, Any]] = []
    for segment in normalized:
        last = compacted[-1] if compacted else None
        if last is None:
            compacted.append(dict(segment))
            continue
        if str(last.get("speaker", "")) == str(segment.get("speaker", "")):
            last["end"] = float(segment.get("end", last.get("end", 0)))
            left = str(last.get("text", ""))
            right = str(segment.get("text", ""))
            last["text"] = f"{left}\n{right}" if left else right
            continue
        compacted.append(dict(segment))
    return compacted


def _normalize_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(segments, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in segments:
        if not isinstance(raw, dict):
            continue
        speaker = str(raw.get("speaker", "UNKNOWN")).strip() or "UNKNOWN"
        text = _sanitize_multiline(raw.get("text", ""))
        try:
            start = float(raw.get("start", 0.0))
        except (TypeError, ValueError):
            start = 0.0
        try:
            end = float(raw.get("end", start))
        except (TypeError, ValueError):
            end = start
        if start < 0:
            start = 0.0
        if end < start:
            end = start
        normalized.append(
            {
                "speaker": speaker,
                "text": text,
                "start": start,
                "end": end,
            }
        )
    return normalized


def _normalize_export_profile(profile: str) -> str:
    normalized = str(profile or "").strip().lower()
    if normalized not in ALLOWED_CORRECTION_EXPORT_PROFILES:
        raise CorrectionExportValidationError(
            "transcript.correction_export_invalid_profile",
            "profile wird nicht unterstuetzt.",
        )
    return normalized


def _normalize_export_format(fmt: str) -> str:
    normalized = str(fmt or "").strip().lower()
    if normalized not in ALLOWED_CORRECTION_EXPORT_FORMATS:
        raise CorrectionExportValidationError(
            "transcript.correction_export_invalid_format",
            "format muss docx|txt sein.",
        )
    return normalized


def _normalize_export_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized == "compact":
        return "compact"
    if normalized in ("", "raw"):
        return "raw"
    raise CorrectionExportValidationError(
        "transcript.correction_export_invalid_mode",
        "mode muss raw|compact sein.",
    )


def _resolve_speaker_label(*, speaker_key: str, speaker_labels: dict[str, str]) -> str:
    alias = str((speaker_labels or {}).get(speaker_key, "")).strip()
    return _sanitize_inline(alias if alias else speaker_key)


def _format_timestamp(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _sanitize_inline(value: Any) -> str:
    cleaned = _sanitize_multiline(value).replace("\n", " ").replace("\r", " ")
    return cleaned.strip()


def _sanitize_multiline(value: Any) -> str:
    raw = str(value or "")
    return "".join(char for char in raw if ord(char) >= 32 or char in {"\n", "\r", "\t"})


def _format_version(value: int | None) -> str:
    try:
        version = int(value) if value is not None else None
    except (TypeError, ValueError):
        version = None
    return str(version) if version is not None and version >= 0 else "-"
