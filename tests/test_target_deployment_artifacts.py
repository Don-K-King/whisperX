from __future__ import annotations

from pathlib import Path
import unittest


class TargetDeploymentArtifactsTests(unittest.TestCase):
    def _read(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def test_compose_defines_required_services_and_preflight_gate(self) -> None:
        compose = self._read("deploy/docker-compose.target.yml")
        dockerfile = self._read("deploy/Dockerfile.runtime")

        for service in (
            "frontend:",
            "api:",
            "worker:",
            "worker-gpu-0:",
            "worker-gpu-1:",
            "worker-cpu:",
            "retention-runner:",
            "retention-preflight:",
            "object-storage-init:",
            "db:",
            "broker:",
            "object-storage:",
            "auth:",
        ):
            self.assertIn(service, compose)

        self.assertIn("RETENTION_VALIDATE_ENV_ONLY=true", compose)
        self.assertIn("service_completed_successfully", compose)
        self.assertIn("WORKER_MODE: ${WORKER_MODE:-whisperx}", compose)
        self.assertIn("WORKER_OBJECT_STORAGE_BASE_URL", compose)
        self.assertIn("WORKER_OBJECT_STORAGE_BUCKET", compose)
        self.assertIn("WORKER_WHISPERX_DEVICE: ${WORKER_WHISPERX_DEVICE:-cuda}", compose)
        self.assertIn("WORKER_WHISPERX_COMPUTE_TYPE: ${WORKER_WHISPERX_COMPUTE_TYPE:-float16}", compose)
        self.assertIn("WORKER_WHISPERX_DEVICE_INDEX: ${WORKER_WHISPERX_DEVICE_INDEX:-0}", compose)
        self.assertIn("WORKER_ALLOWED_QUEUES", compose)
        self.assertIn("gpus: all", compose)
        self.assertIn("WORKER_WHISPERX_TIMEOUT_SECONDS: ${WORKER_WHISPERX_TIMEOUT_SECONDS:-0}", compose)
        self.assertIn("mc mb --ignore-existing local/uploads", compose)
        self.assertIn("PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu128", dockerfile)

    def test_env_profiles_document_required_and_optional_variables_per_service(self) -> None:
        env_example = self._read(".env.example")
        env_prod = self._read(".env.production.example")

        for marker in (
            "# API (Pflicht)",
            "# Worker (Pflicht)",
            "# Retention Runner (Pflicht)",
            "# Auth/Keycloak (Pflicht)",
            "# Optional",
        ):
            self.assertIn(marker, env_example)

        for required in (
            "API_DB_DSN=",
            "WORKER_BROKER_URL=",
            "WORKER_WHISPERX_DEVICE=cuda",
            "WORKER_WHISPERX_COMPUTE_TYPE=float16",
            "WORKER_WHISPERX_DEVICE_INDEX=0",
            "WORKER_ALLOWED_QUEUES=",
            "RETENTION_VALIDATE_ENV_ONLY=false",
            "KEYCLOAK_ADMIN_PASSWORD=",
        ):
            self.assertIn(required, env_prod)

    def test_runbook_covers_provisioning_secrets_healthchecks_and_rollback(self) -> None:
        runbook = self._read("docs/operations/runbooks.md")
        monitoring = self._read("docs/operations/monitoring-alerting.md")

        for heading in (
            "## 2026-03-08 – Zielbetrieb mit Docker Compose (API/Worker/Retention)",
            "### 1) Provisioning",
            "### 2) Secret-Handling",
            "### 3) Startreihenfolge",
            "### 4) Healthchecks",
            "### 5) Rollback",
        ):
            self.assertIn(heading, runbook)

        for mapping in (
            "docker compose service `api`",
            "docker compose service `worker`",
            "docker compose service `retention-runner`",
            "Alert-Rule `retention_runner_preflight_failed`",
        ):
            self.assertIn(mapping, monitoring)


if __name__ == "__main__":
    unittest.main()
