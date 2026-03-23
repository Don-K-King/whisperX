from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

from evodox.runtime.api_app import create_app_from_env
from evodox.runtime.worker_runner import WorkerRuntime, WorkerRuntimeSettings
from evodox.jobs.worker_pipeline_service import WorkerPipeline


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
            self.assertEqual(body["speaker_labels"], {})

            jobs = client.get("/api/v1/jobs", headers={"Authorization": "Bearer dev:tenant-a:user:u-1"})
            self.assertEqual(jobs.status_code, 200)
            self.assertTrue(any(item["job_id"] == job_id for item in jobs.json()["jobs"]))

            audit = client.get("/api/v1/audit", headers={"Authorization": "Bearer dev:tenant-a:admin:u-admin"})
            self.assertEqual(audit.status_code, 200)

    def test_pause_resume_uses_checkpoint_and_completes(self) -> None:
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
            headers = {"Authorization": "Bearer dev:tenant-a:user:u-1"}

            created = client.post(
                "/api/v1/jobs",
                headers={**headers, "Idempotency-Key": "idem-create-pause-1"},
                json={
                    "filename": "checkpoint.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 2048,
                    "retention_months": 6,
                },
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["job_id"]

            completed = client.post(
                f"/api/v1/jobs/{job_id}/complete-upload",
                headers={**headers, "Idempotency-Key": "idem-complete-pause-1"},
                json={
                    "upload_session_id": created.json()["upload"]["session_id"],
                    "object_key": f"tenant/tenant-a/{job_id}/checkpoint.mp4",
                    "checksum_sha256": "a" * 64,
                },
            )
            self.assertEqual(completed.status_code, 200)

            worker = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            pause_once = {"enabled": True}
            seen_offsets: list[int] = []

            def asr_engine(_object_key: str, *, stage_offset: int = 0):
                seen_offsets.append(stage_offset)
                if pause_once["enabled"]:
                    pause_once["enabled"] = False
                    worker.job_repository.set_status("tenant-a", job_id, "pause_requested", progress=20)
                return {
                    "text": "seg0 seg1 seg2",
                    "language": "de",
                    "segments": [
                        {"start": 0.0, "end": 1.0, "text": "seg0"},
                        {"start": 1.0, "end": 2.0, "text": "seg1"},
                        {"start": 2.0, "end": 3.0, "text": "seg2"},
                    ][stage_offset:],
                }

            worker.pipeline = WorkerPipeline(
                job_store=worker.job_repository,
                artifact_store=worker.artifact_store,
                checkpoint_store=worker.checkpoint_store,
                audit_log=worker.audit_log,
                asr_engine=asr_engine,
                align_engine=lambda transcript: {"segments": transcript["segments"]},
                diarize_engine=lambda aligned: {"segments": [{"speaker": "SPEAKER_00"} for _ in aligned["segments"]]},
            )

            first_tick = worker.run_once()
            self.assertEqual(first_tick.processed, 1)
            paused_status = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            self.assertEqual(paused_status.status_code, 200)
            self.assertEqual(paused_status.json()["status"], "paused")

            resumed = client.post(f"/api/v1/jobs/{job_id}/resume", headers=headers)
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(resumed.json()["status"], "queued")

            second_tick = worker.run_once()
            self.assertEqual(second_tick.processed, 1)
            final_status = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            self.assertEqual(final_status.status_code, 200)
            self.assertEqual(final_status.json()["status"], "completed")
            self.assertEqual(seen_offsets, [0, 1])

    def test_cancel_flow_reaches_terminal_canceled_without_further_progress(self) -> None:
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
            headers = {"Authorization": "Bearer dev:tenant-a:user:u-1"}

            created = client.post(
                "/api/v1/jobs",
                headers={**headers, "Idempotency-Key": "idem-create-cancel-1"},
                json={
                    "filename": "cancel.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 2048,
                    "retention_months": 6,
                },
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["job_id"]

            completed = client.post(
                f"/api/v1/jobs/{job_id}/complete-upload",
                headers={**headers, "Idempotency-Key": "idem-complete-cancel-1"},
                json={
                    "upload_session_id": created.json()["upload"]["session_id"],
                    "object_key": f"tenant/tenant-a/{job_id}/cancel.mp4",
                    "checksum_sha256": "a" * 64,
                },
            )
            self.assertEqual(completed.status_code, 200)

            worker = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )

            def asr_engine(_object_key: str):
                worker.job_repository.set_status("tenant-a", job_id, "cancel_requested", progress=25)
                return {
                    "text": "cancel-me",
                    "segments": [{"start": 0.0, "end": 1.0, "text": "cancel-me"}],
                }

            worker.pipeline = WorkerPipeline(
                job_store=worker.job_repository,
                artifact_store=worker.artifact_store,
                checkpoint_store=worker.checkpoint_store,
                audit_log=worker.audit_log,
                asr_engine=asr_engine,
                align_engine=lambda transcript: transcript,
                diarize_engine=lambda aligned: aligned,
            )

            tick = worker.run_once()
            self.assertEqual(tick.processed, 1)
            canceled = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            self.assertEqual(canceled.status_code, 200)
            self.assertEqual(canceled.json()["status"], "canceled")

            second_tick = worker.run_once()
            self.assertEqual(second_tick.processed, 0)
            still_canceled = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            self.assertEqual(still_canceled.status_code, 200)
            self.assertEqual(still_canceled.json()["status"], "canceled")

    def test_delete_processing_job_is_allowed_and_terminal(self) -> None:
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
            headers = {"Authorization": "Bearer dev:tenant-a:user:u-1"}

            created = client.post(
                "/api/v1/jobs",
                headers={**headers, "Idempotency-Key": "idem-create-delete-1"},
                json={
                    "filename": "delete-active.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 2048,
                    "retention_months": 6,
                },
            )
            self.assertEqual(created.status_code, 200)
            job_id = created.json()["job_id"]

            completed = client.post(
                f"/api/v1/jobs/{job_id}/complete-upload",
                headers={**headers, "Idempotency-Key": "idem-complete-delete-1"},
                json={
                    "upload_session_id": created.json()["upload"]["session_id"],
                    "object_key": f"tenant/tenant-a/{job_id}/delete-active.mp4",
                    "checksum_sha256": "a" * 64,
                },
            )
            self.assertEqual(completed.status_code, 200)

            worker = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            worker.job_repository.set_status("tenant-a", job_id, "processing", progress=20)

            deleted = client.delete(f"/api/v1/jobs/{job_id}", headers=headers)
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(deleted.json()["status"], "deleted")


if __name__ == "__main__":
    unittest.main()
