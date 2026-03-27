from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any, Callable

from evodox.jobs.infrastructure import (
    JsonlAuditLog,
    LenientObjectStorageCatalog,
    LocalObjectStorageCatalog,
    LocalPresignUploadSessionFactory,
    SQLiteCompleteUploadIdempotencyStore,
    SQLiteIdempotencyStore,
    SQLiteJobCheckpointStore,
    SQLiteJobRepository,
    SQLiteOutbox,
    SQLiteTenantTranscriptionSettingsStore,
    SQLiteTranscriptRepository,
    SQLiteWorkerArtifactStore,
)
from evodox.jobs.transcript_correction_store import SQLiteTranscriptCorrectionStore
from evodox.web.fastapi_adapter import FastAPIAdapterSettings, create_fastapi_app


class APIRuntimeConfigError(ValueError):
    pass


@dataclass(frozen=True)
class APIRuntimeSettings:
    db_path: Path
    audit_log_path: Path
    auth_mode: str
    expected_issuer: str
    expected_audience: str
    upload_base_url: str
    upload_bucket: str
    upload_signing_secret: str
    object_storage_mode: str
    dev_default_tenant: str
    dev_default_sub: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "APIRuntimeSettings":
        source = env if env is not None else os.environ

        db_path = Path(source.get("API_DB_PATH", "/runtime/jobs.db").strip())
        audit_log_path = Path(source.get("API_AUDIT_LOG_PATH", "/runtime/audit/api-audit.jsonl").strip())

        auth_mode = source.get("API_AUTH_MODE", "oidc").strip().lower()
        if auth_mode not in {"oidc", "dev"}:
            raise APIRuntimeConfigError("API_AUTH_MODE muss 'oidc' oder 'dev' sein.")

        expected_issuer = source.get("API_AUTH_ISSUER", "").strip()
        expected_audience = source.get("API_AUTH_AUDIENCE", "").strip()
        if not expected_issuer:
            raise APIRuntimeConfigError("API_AUTH_ISSUER ist erforderlich.")
        if not expected_audience:
            raise APIRuntimeConfigError("API_AUTH_AUDIENCE ist erforderlich.")

        upload_base_url = source.get("API_UPLOAD_BASE_URL", "http://object-storage:9000").strip()
        upload_bucket = source.get("API_UPLOAD_BUCKET", "uploads").strip()
        upload_signing_secret = source.get("API_UPLOAD_SIGNING_SECRET", "dev-only-secret").strip()
        if not upload_bucket:
            raise APIRuntimeConfigError("API_UPLOAD_BUCKET ist erforderlich.")
        if not upload_base_url:
            raise APIRuntimeConfigError("API_UPLOAD_BASE_URL ist erforderlich.")

        object_storage_mode = source.get("API_OBJECT_STORAGE_MODE", "strict").strip().lower()
        if object_storage_mode not in {"strict", "stub"}:
            raise APIRuntimeConfigError("API_OBJECT_STORAGE_MODE muss 'strict' oder 'stub' sein.")

        dev_default_tenant = source.get("API_DEV_DEFAULT_TENANT", "tenant-a").strip()
        dev_default_sub = source.get("API_DEV_DEFAULT_SUB", "dev-user").strip()
        if not dev_default_tenant:
            raise APIRuntimeConfigError("API_DEV_DEFAULT_TENANT darf nicht leer sein.")
        if not dev_default_sub:
            raise APIRuntimeConfigError("API_DEV_DEFAULT_SUB darf nicht leer sein.")

        return cls(
            db_path=db_path,
            audit_log_path=audit_log_path,
            auth_mode=auth_mode,
            expected_issuer=expected_issuer,
            expected_audience=expected_audience,
            upload_base_url=upload_base_url,
            upload_bucket=upload_bucket,
            upload_signing_secret=upload_signing_secret,
            object_storage_mode=object_storage_mode,
            dev_default_tenant=dev_default_tenant,
            dev_default_sub=dev_default_sub,
        )


def build_token_verifier(settings: APIRuntimeSettings) -> Callable[[str], dict[str, Any]]:
    if settings.auth_mode == "dev":
        return _build_dev_token_verifier(settings)
    return _build_oidc_payload_verifier()


def create_app_from_env(env: dict[str, str] | None = None):
    settings = APIRuntimeSettings.from_env(env)
    return create_app(settings=settings)


def create_app(*, settings: APIRuntimeSettings | None = None):
    runtime_settings = settings or APIRuntimeSettings.from_env()
    runtime_settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    object_storage: Any
    if runtime_settings.object_storage_mode == "stub":
        object_storage = LenientObjectStorageCatalog()
    else:
        object_storage = LocalObjectStorageCatalog()

    transcript_repository = SQLiteTranscriptRepository(runtime_settings.db_path)
    correction_store = SQLiteTranscriptCorrectionStore(runtime_settings.db_path)
    checkpoint_store = SQLiteJobCheckpointStore(runtime_settings.db_path)
    worker_artifact_store = SQLiteWorkerArtifactStore(runtime_settings.db_path)

    return create_fastapi_app(
        settings=FastAPIAdapterSettings(
            expected_issuer=runtime_settings.expected_issuer,
            expected_audience=runtime_settings.expected_audience,
        ),
        token_verifier=build_token_verifier(runtime_settings),
        job_repository=SQLiteJobRepository(runtime_settings.db_path),
        upload_session_factory=LocalPresignUploadSessionFactory(
            base_url=runtime_settings.upload_base_url,
            bucket=runtime_settings.upload_bucket,
            signing_secret=runtime_settings.upload_signing_secret,
        ),
        audit_log=JsonlAuditLog(runtime_settings.audit_log_path),
        idempotency_store=SQLiteIdempotencyStore(runtime_settings.db_path),
        complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(runtime_settings.db_path),
        object_storage=object_storage,
        outbox=SQLiteOutbox(runtime_settings.db_path),
        transcript_repository=transcript_repository,
        transcript_correction_store=correction_store,
        checkpoint_store=checkpoint_store,
        worker_artifact_store=worker_artifact_store,
        transcription_settings_store=SQLiteTenantTranscriptionSettingsStore(runtime_settings.db_path),
        media_base_url=runtime_settings.upload_base_url,
        media_bucket=runtime_settings.upload_bucket,
    )


def _build_oidc_payload_verifier() -> Callable[[str], dict[str, Any]]:
    def _verify(token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid JWT format")
        payload = _decode_b64url_json(parts[1])
        payload.setdefault("now", int(time.time()))
        return payload

    return _verify


def _build_dev_token_verifier(settings: APIRuntimeSettings) -> Callable[[str], dict[str, Any]]:
    def _verify(token: str) -> dict[str, Any]:
        now = int(time.time())
        if token.startswith("dev:"):
            # dev:<tenant_id>:<role1,role2>:<sub>
            parts = token.split(":")
            if len(parts) >= 4:
                tenant_id = parts[1].strip() or settings.dev_default_tenant
                roles = [role for role in parts[2].split(",") if role]
                sub = parts[3].strip() or settings.dev_default_sub
            else:
                tenant_id = settings.dev_default_tenant
                roles = ["user"]
                sub = settings.dev_default_sub
        elif token == "dev-admin":
            tenant_id = settings.dev_default_tenant
            roles = ["admin"]
            sub = "dev-admin"
        elif token == "dev-reviewer":
            tenant_id = settings.dev_default_tenant
            roles = ["reviewer"]
            sub = "dev-reviewer"
        else:
            tenant_id = settings.dev_default_tenant
            roles = ["user"]
            sub = settings.dev_default_sub

        return {
            "sub": sub,
            "tenant_id": tenant_id,
            "roles": roles,
            "iss": settings.expected_issuer,
            "aud": settings.expected_audience,
            "exp": now + 3600,
            "iat": now - 1,
            "nbf": now - 1,
            "now": now,
        }

    return _verify


def _decode_b64url_json(raw: str) -> dict[str, Any]:
    padded = raw + "=" * (-len(raw) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("Token payload must be an object.")
    return payload


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("Use: uvicorn evodox.runtime.api_app:create_app --factory")
