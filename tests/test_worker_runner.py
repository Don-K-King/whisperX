from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from evodox.jobs.infrastructure import SQLiteJobRepository, SQLiteOutbox
from evodox.runtime.worker_runner import WorkerRuntime, WorkerRuntimeSettings


class WorkerRunnerTests(unittest.TestCase):
    def test_run_once_processes_pending_outbox_event_to_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_1/audio.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_1",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_1/audio.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_1",
                }
            )

            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            result = runtime.run_once()

            self.assertEqual(result.processed, 1)
            row = repo.get("tenant-a", "job_1")
            self.assertEqual(row["status"], "completed")
            with sqlite3.connect(db_path) as conn:
                outbox_status = conn.execute("SELECT status FROM outbox_events WHERE job_id = 'job_1'").fetchone()[0]
            self.assertEqual(outbox_status, "published")

    def test_scope_violation_marks_job_failed_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_2",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-b/job_2/audio.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_2",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-b/job_2/audio.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_2",
                }
            )

            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            result = runtime.run_once()

            self.assertEqual(result.processed, 1)
            row = repo.get("tenant-a", "job_2")
            self.assertEqual(row["status"], "failed_terminal")


if __name__ == "__main__":
    unittest.main()
