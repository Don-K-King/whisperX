import tempfile
import unittest
from pathlib import Path

from evodox.jobs.infrastructure import JsonlAuditLog, SQLiteJobRepository, SQLiteOutbox
from evodox.jobs.lifecycle_service import JobLifecycleError, delete_job, pause_job, resume_job


class _DeleteAwareStorage:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete_prefix(self, *, tenant_id: str, object_prefix: str) -> bool:
        self.deleted.append((tenant_id, object_prefix))
        return True


class JobLifecycleServiceTests(unittest.TestCase):
    def test_pause_processing_sets_pause_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "run.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "processing",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_1/run.mp4",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_1",
                }
            )

            status = pause_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_1",
                job_store=repo,
                outbox=SQLiteOutbox(db_path),
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )

            self.assertEqual(status, "pause_requested")
            self.assertEqual(repo.get("tenant-a", "job_1")["status"], "pause_requested")

    def test_resume_from_paused_is_idempotent_and_emits_single_queued_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_2",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "resume.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "paused",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_2/resume.mp4",
                    "checksum_sha256": "b" * 64,
                    "upload_session_id": "up_2",
                }
            )

            first = resume_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_2",
                job_store=repo,
                outbox=outbox,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )
            second = resume_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_2",
                job_store=repo,
                outbox=outbox,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )

            self.assertEqual(first, "queued")
            self.assertEqual(second, "queued")
            self.assertEqual(repo.get("tenant-a", "job_2")["status"], "queued")
            self.assertEqual(len(outbox.list_pending(limit=20)), 1)

    def test_delete_active_job_raises_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_3",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "active.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "processing",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_3/active.mp4",
                    "checksum_sha256": "c" * 64,
                    "upload_session_id": "up_3",
                }
            )

            with self.assertRaises(JobLifecycleError) as exc:
                delete_job(
                    tenant_id="tenant-a",
                    actor_id="u-1",
                    job_id="job_3",
                    job_store=repo,
                    outbox=SQLiteOutbox(db_path),
                    object_storage=_DeleteAwareStorage(),
                    audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
                )
            self.assertEqual(exc.exception.error_code, "job.delete.active_conflict")

    def test_delete_completed_job_soft_deletes_and_prunes_pending_outbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            storage = _DeleteAwareStorage()
            repo.create(
                {
                    "job_id": "job_4",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "done.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "completed",
                    "progress": 100,
                    "object_key": "tenant/tenant-a/job_4/done.mp4",
                    "checksum_sha256": "d" * 64,
                    "upload_session_id": "up_4",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_4",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_4/done.mp4",
                    "checksum_sha256": "d" * 64,
                    "upload_session_id": "up_4",
                }
            )

            status = delete_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_4",
                job_store=repo,
                outbox=outbox,
                object_storage=storage,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )

            self.assertEqual(status, "deleted")
            row = repo.get("tenant-a", "job_4")
            self.assertEqual(row["status"], "deleted")
            self.assertEqual(outbox.list_pending(limit=20), [])
            self.assertEqual(storage.deleted[0], ("tenant-a", "tenant/tenant-a/job_4/"))


if __name__ == "__main__":
    unittest.main()
