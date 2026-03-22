from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

from evodox.runtime.api_app import create_app_from_env
from evodox.runtime.worker_runner import WorkerRuntime, WorkerRuntimeSettings


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "fastapi not installed in this environment")
class LocalRuntimeSmokeTests(unittest.TestCase):
    def test_create_complete_and_worker_tick_to_completed(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            app = create_app_from_env(
                {
                    "API_DB_PATH": str(db_path),
                    "API_AUDIT_LOG_PATH": str(Path(tmpdir) / "api-audit.jsonl"),
                    "API_AUTH_MODE": "dev",
                    "API_AUTH_ISSUER": "https://issuer.local/realms/evodox",
                    "API_AUTH_AUDIENCE": "evodox-api",
                    "API_UPLOAD_BASE_URL": "http://object-storage:9000",
                    "API_UPLOAD_BUCKET": "uploads",
                    "API_UPLOAD_SIGNING_SECRET": "dev-secret",
                    "API_OBJECT_STORAGE_MODE": "stub",
                    "API_DEV_DEFAULT_TENANT": "tenant-a",
                }
            )
            client = TestClient(app)

            created = client.post(
                "/api/v1/jobs",
                headers={
                    "Authorization": "Bearer dev:tenant-a:user:u-1",
                    "Idempotency-Key": "idem-create-1",
                },
                json={
                    "filename": "meeting.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 2048,
                    "retention_months": 6,
                },
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["job_id"]

            completed = client.post(
                f"/api/v1/jobs/{job_id}/complete-upload",
                headers={
                    "Authorization": "Bearer dev:tenant-a:user:u-1",
                    "Idempotency-Key": "idem-complete-1",
                },
                json={
                    "upload_session_id": created.json()["upload"]["session_id"],
                    "object_key": f"tenant/tenant-a/{job_id}/meeting.mp4",
                    "checksum_sha256": "a" * 64,
                },
            )
            self.assertEqual(completed.status_code, 200)
            self.assertEqual(completed.json()["status"], "queued")

            worker = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            tick = worker.run_once()
            self.assertEqual(tick.processed, 1)

            status = client.get(
                f"/api/v1/jobs/{job_id}",
                headers={"Authorization": "Bearer dev:tenant-a:user:u-1"},
            )
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "completed")

            transcript = client.get(
                f"/api/v1/jobs/{job_id}/transcript",
                headers={"Authorization": "Bearer dev:tenant-a:user:u-1"},
            )
            self.assertEqual(transcript.status_code, 200)
            body = transcript.json()
            self.assertEqual(body["job_id"], job_id)
            self.assertEqual(body["version"], 1)
            self.assertGreaterEqual(len(body["segments"]), 1)
            self.assertEqual(body["segments"][0]["speaker"], "SPEAKER_00")
            self.assertIn("Stub transcript", body["segments"][0]["text"])

            jobs = client.get("/api/v1/jobs", headers={"Authorization": "Bearer dev:tenant-a:user:u-1"})
            self.assertEqual(jobs.status_code, 200)
            self.assertTrue(any(item["job_id"] == job_id for item in jobs.json()["jobs"]))

            audit = client.get("/api/v1/audit", headers={"Authorization": "Bearer dev:tenant-a:admin:u-admin"})
            self.assertEqual(audit.status_code, 200)


if __name__ == "__main__":
    unittest.main()
