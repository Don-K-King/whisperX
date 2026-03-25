from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from evodox.runtime.api_app import APIRuntimeSettings, build_token_verifier, create_app_from_env


class RuntimeEntrypointsTests(unittest.TestCase):
    def test_compose_uses_runtime_factories_for_api_and_worker(self) -> None:
        compose = Path("deploy/docker-compose.target.yml").read_text(encoding="utf-8")
        self.assertIn("evodox.runtime.api_app:create_app", compose)
        self.assertIn("evodox.runtime.worker_runner", compose)

    def test_api_runtime_uses_dev_token_verifier_when_configured(self) -> None:
        settings = APIRuntimeSettings.from_env(
            {
                "API_DB_PATH": "/tmp/evodox.db",
                "API_AUDIT_LOG_PATH": "/tmp/evodox-audit.jsonl",
                "API_AUTH_MODE": "dev",
                "API_AUTH_ISSUER": "https://issuer.local/realms/evodox",
                "API_AUTH_AUDIENCE": "evodox-api",
                "API_UPLOAD_BASE_URL": "http://minio.local",
                "API_UPLOAD_BUCKET": "uploads",
                "API_UPLOAD_SIGNING_SECRET": "dev-secret",
                "API_OBJECT_STORAGE_MODE": "stub",
                "API_DEV_DEFAULT_TENANT": "tenant-a",
                "API_DEV_DEFAULT_SUB": "dev-user",
            }
        )
        claims = build_token_verifier(settings)("dev:tenant-x:admin,user:alice")

        self.assertEqual(claims["tenant_id"], "tenant-x")
        self.assertEqual(claims["roles"], ["admin", "user"])
        self.assertEqual(claims["sub"], "alice")
        self.assertEqual(claims["iss"], "https://issuer.local/realms/evodox")

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "fastapi not installed in this environment")
    def test_api_factory_can_be_created_from_env_without_manual_di(self) -> None:
        app = create_app_from_env(
            {
                "API_DB_PATH": "/tmp/evodox.db",
                "API_AUDIT_LOG_PATH": "/tmp/evodox-audit.jsonl",
                "API_AUTH_MODE": "dev",
                "API_AUTH_ISSUER": "https://issuer.local/realms/evodox",
                "API_AUTH_AUDIENCE": "evodox-api",
                "API_UPLOAD_BASE_URL": "http://minio.local",
                "API_UPLOAD_BUCKET": "uploads",
                "API_UPLOAD_SIGNING_SECRET": "dev-secret",
                "API_OBJECT_STORAGE_MODE": "stub",
            }
        )

        self.assertEqual(app.title, "EvidoX API")


if __name__ == "__main__":
    unittest.main()
