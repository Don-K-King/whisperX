from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any


DEFAULT_DECODING_OPTIONS: dict[str, Any] = {
    "temperature": 0.0,
    "beam_size": 5,
    "patience": 1.0,
    "length_penalty": 1.0,
    "compression_ratio_threshold": 2.4,
    "logprob_threshold": -1.0,
    "no_speech_threshold": 0.6,
    "suppress_tokens": "-1",
    "initial_prompt": "",
    "condition_on_previous_text": False,
    "chunk_size": 30,
    "vad_onset": 0.5,
    "vad_offset": 0.363,
    "language": "auto",
}

_FLOAT_RANGES: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 1.0),
    "patience": (0.1, 2.0),
    "length_penalty": (0.1, 2.0),
    "compression_ratio_threshold": (0.5, 5.0),
    "logprob_threshold": (-5.0, 0.0),
    "no_speech_threshold": (0.0, 1.0),
    "vad_onset": (0.0, 1.0),
    "vad_offset": (0.0, 1.0),
}
_INT_RANGES: dict[str, tuple[int, int]] = {
    "beam_size": (1, 10),
    "chunk_size": (5, 60),
}
_ALLOWED_LANGUAGES = frozenset({"auto", "de", "en", "fr", "es", "it"})


class TranscriptionSettingsValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


@dataclass(frozen=True)
class TenantTranscriptionSettingsRecord:
    tenant_id: str
    decoding_options: dict[str, Any]
    updated_at: str
    updated_by: str


class InMemoryTenantTranscriptionSettingsStore:
    def __init__(self) -> None:
        self._rows: dict[str, TenantTranscriptionSettingsRecord] = {}

    def get(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._rows.get(tenant_id)
        if row is None:
            return None
        return {
            "tenant_id": row.tenant_id,
            "decoding_options": dict(row.decoding_options),
            "updated_at": row.updated_at,
            "updated_by": row.updated_by,
        }

    def upsert(self, *, tenant_id: str, updated_by: str, decoding_options: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(tz=timezone.utc).isoformat()
        row = TenantTranscriptionSettingsRecord(
            tenant_id=tenant_id,
            decoding_options=dict(decoding_options),
            updated_at=now,
            updated_by=str(updated_by or ""),
        )
        self._rows[tenant_id] = row
        return {
            "tenant_id": row.tenant_id,
            "decoding_options": dict(row.decoding_options),
            "updated_at": row.updated_at,
            "updated_by": row.updated_by,
        }


def normalize_decoding_options(payload: Any) -> dict[str, Any]:
    data = {} if payload is None else payload
    if not isinstance(data, dict):
        raise TranscriptionSettingsValidationError(
            "transcription_settings.invalid_payload",
            "Decoding options muessen ein Objekt sein.",
        )

    unknown = [key for key in data.keys() if key not in DEFAULT_DECODING_OPTIONS]
    if unknown:
        raise TranscriptionSettingsValidationError(
            "transcription_settings.invalid_payload",
            f"Unbekannte Decoding-Option(en): {', '.join(sorted(unknown))}",
        )

    normalized = dict(DEFAULT_DECODING_OPTIONS)

    for key, (lower, upper) in _FLOAT_RANGES.items():
        if key not in data:
            continue
        value = _coerce_float(data[key], key=key)
        if value < lower or value > upper:
            raise TranscriptionSettingsValidationError(
                "transcription_settings.invalid_payload",
                f"{key} muss zwischen {lower} und {upper} liegen.",
            )
        normalized[key] = value

    for key, (lower, upper) in _INT_RANGES.items():
        if key not in data:
            continue
        value = _coerce_int(data[key], key=key)
        if value < lower or value > upper:
            raise TranscriptionSettingsValidationError(
                "transcription_settings.invalid_payload",
                f"{key} muss zwischen {lower} und {upper} liegen.",
            )
        normalized[key] = value

    if "suppress_tokens" in data:
        normalized["suppress_tokens"] = _normalize_suppress_tokens(data["suppress_tokens"])

    if "initial_prompt" in data:
        prompt = str(data["initial_prompt"] or "")
        if len(prompt) > 500:
            raise TranscriptionSettingsValidationError(
                "transcription_settings.invalid_payload",
                "initial_prompt darf maximal 500 Zeichen enthalten.",
            )
        normalized["initial_prompt"] = prompt

    if "condition_on_previous_text" in data:
        raw = data["condition_on_previous_text"]
        if not isinstance(raw, bool):
            raise TranscriptionSettingsValidationError(
                "transcription_settings.invalid_payload",
                "condition_on_previous_text muss bool sein.",
            )
        normalized["condition_on_previous_text"] = raw

    if "language" in data:
        language = str(data["language"] or "").strip().lower()
        if language not in _ALLOWED_LANGUAGES:
            raise TranscriptionSettingsValidationError(
                "transcription_settings.invalid_payload",
                f"language muss einer von {', '.join(sorted(_ALLOWED_LANGUAGES))} sein.",
            )
        normalized["language"] = language

    return normalized


def safe_worker_decoding_options(payload: Any) -> dict[str, Any]:
    try:
        return normalize_decoding_options(payload)
    except TranscriptionSettingsValidationError:
        return dict(DEFAULT_DECODING_OPTIONS)


def get_transcription_settings(
    *,
    tenant_id: str,
    actor_id: str,
    settings_store: Any,
    audit_log: Any,
) -> dict[str, Any]:
    current = settings_store.get(tenant_id) if hasattr(settings_store, "get") else None
    options = safe_worker_decoding_options((current or {}).get("decoding_options"))
    response = {
        "tenant_id": tenant_id,
        "decoding_options": options,
        "updated_at": (current or {}).get("updated_at"),
        "updated_by": (current or {}).get("updated_by"),
    }
    _audit_append(
        audit_log,
        {
            "action": "transcription_settings.read",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "options_hash": _hash_options(options),
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    return response


def update_transcription_settings(
    *,
    tenant_id: str,
    actor_id: str,
    payload: Any,
    settings_store: Any,
    audit_log: Any,
) -> dict[str, Any]:
    normalized = normalize_decoding_options(payload)
    if not hasattr(settings_store, "upsert"):
        raise TranscriptionSettingsValidationError(
            "transcription_settings.unavailable",
            "Settings-Store nicht verfuegbar.",
        )
    saved = settings_store.upsert(tenant_id=tenant_id, updated_by=actor_id, decoding_options=normalized)
    _audit_append(
        audit_log,
        {
            "action": "transcription_settings.updated",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "options_hash": _hash_options(normalized),
            "initial_prompt_len": len(str(normalized.get("initial_prompt") or "")),
            "initial_prompt_sha256": _hash_prompt(str(normalized.get("initial_prompt") or "")),
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    return {
        "tenant_id": tenant_id,
        "decoding_options": dict(saved["decoding_options"]),
        "updated_at": saved.get("updated_at"),
        "updated_by": saved.get("updated_by"),
    }


def _coerce_float(raw: Any, *, key: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise TranscriptionSettingsValidationError(
            "transcription_settings.invalid_payload",
            f"{key} muss numerisch sein.",
        ) from exc


def _coerce_int(raw: Any, *, key: str) -> int:
    if isinstance(raw, bool):
        raise TranscriptionSettingsValidationError(
            "transcription_settings.invalid_payload",
            f"{key} muss ganzzahlig sein.",
        )
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise TranscriptionSettingsValidationError(
            "transcription_settings.invalid_payload",
            f"{key} muss ganzzahlig sein.",
        ) from exc
    return value


def _normalize_suppress_tokens(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        raise TranscriptionSettingsValidationError(
            "transcription_settings.invalid_payload",
            "suppress_tokens darf nicht leer sein.",
        )
    parts = [item.strip() for item in value.split(",")]
    if any(not part for part in parts):
        raise TranscriptionSettingsValidationError(
            "transcription_settings.invalid_payload",
            "suppress_tokens CSV ist ungueltig.",
        )
    for part in parts:
        try:
            int(part)
        except ValueError as exc:
            raise TranscriptionSettingsValidationError(
                "transcription_settings.invalid_payload",
                "suppress_tokens CSV muss nur Integer enthalten.",
            ) from exc
    return ",".join(parts)


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _hash_options(options: dict[str, Any]) -> str:
    canonical = str(sorted(options.items()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _audit_append(audit_log: Any, payload: dict[str, Any]) -> None:
    append = getattr(audit_log, "append", None)
    if callable(append):
        append(payload)
