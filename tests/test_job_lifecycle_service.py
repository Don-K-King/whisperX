import json
import tempfile
import unittest
from pathlib import Path

from evodox.jobs.infrastructure import JsonlAuditLog, SQLiteJobRepository, SQLiteOutbox
from evodox.jobs.lifecycle_service import JobLifecycleError, cancel_job, delete_job, pause_job, resume_job


class _DeleteAwareStorage:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete_prefix(self, *, tenant_id: str, object_prefix: str) -> bool:
        self.deleted.append((tenant_id, object_prefix))
        return True


class _DeleteAwareStore:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete(self, tenant_id: str, job_id: str) -> None:
        self.deleted.append((tenant_id, job_id))


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
                    "transcription_options_json": json.dumps(
                        {
                            "temperature": 0.2,
                            "beam_size": 4,
                            "patience": 1.0,
                            "length_penalty": 1.0,
                            "compression_ratio_threshold": 2.4,
                            "logprob_threshold": -1.0,
                            "no_speech_threshold": 0.6,
                            "suppress_tokens": "-1",
                            "initial_prompt": "Mit Fachsprache arbeiten",
                            "condition_on_previous_text": False,
                        },
                        sort_keys=True,
                    ),
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
            pending = outbox.list_pending(limit=20)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["payload"]["transcription_options"]["beam_size"], 4)

    def test_cancel_processing_sets_cancel_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_cancel_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "run.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "processing",
                    "progress": 48,
                    "object_key": "tenant/tenant-a/job_cancel_1/run.mp4",
                    "checksum_sha256": "b" * 64,
                    "upload_session_id": "up_cancel_1",
                }
            )

            status = cancel_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_cancel_1",
                job_store=repo,
                outbox=SQLiteOutbox(db_path),
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )

            self.assertEqual(status, "cancel_requested")
            row = repo.get("tenant-a", "job_cancel_1")
            self.assertEqual(row["status"], "cancel_requested")
            self.assertEqual(row["progress"], 48)

    def test_cancel_paused_transitions_to_canceled_and_prunes_pending_outbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_cancel_2",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "pause.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "paused",
                    "progress": 35,
                    "object_key": "tenant/tenant-a/job_cancel_2/pause.mp4",
                    "checksum_sha256": "c" * 64,
                    "upload_session_id": "up_cancel_2",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_cancel_2",
                    "queue": "cpu-short",
                    "upload_session_id": "up_cancel_2",
                    "object_key": "tenant/tenant-a/job_cancel_2/pause.mp4",
                    "checksum_sha256": "c" * 64,
                }
            )

            status = cancel_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_cancel_2",
                job_store=repo,
                outbox=outbox,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )

            self.assertEqual(status, "canceled")
            row = repo.get("tenant-a", "job_cancel_2")
            self.assertEqual(row["status"], "canceled")
            self.assertEqual(row["progress"], 100)
            self.assertEqual(outbox.list_pending(limit=20), [])

    def test_resume_canceled_job_returns_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_cancel_3",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "cancel.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "canceled",
                    "progress": 100,
                    "object_key": "tenant/tenant-a/job_cancel_3/cancel.mp4",
                    "checksum_sha256": "d" * 64,
                    "upload_session_id": "up_cancel_3",
                }
            )

            with self.assertRaises(JobLifecycleError) as exc:
                resume_job(
                    tenant_id="tenant-a",
                    actor_id="u-1",
                    job_id="job_cancel_3",
                    job_store=repo,
                    outbox=SQLiteOutbox(db_path),
                    audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
                )
            self.assertEqual(exc.exception.error_code, "job.resume.invalid_state")

    def test_resume_from_paused_without_snapshot_uses_default_decoding_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_resume_defaults",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "resume.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "paused",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_resume_defaults/resume.wav",
                    "checksum_sha256": "c" * 64,
                    "upload_session_id": "up_resume_defaults",
                }
            )

            status = resume_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_resume_defaults",
                job_store=repo,
                outbox=outbox,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )

            self.assertEqual(status, "queued")
            pending = outbox.list_pending(limit=20)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["payload"]["transcription_options"]["beam_size"], 5)

    def test_delete_processing_job_soft_deletes_and_prunes_pending_outbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            storage = _DeleteAwareStorage()
            checkpoint_store = _DeleteAwareStore()
            artifact_store = _DeleteAwareStore()
            transcript_store = _DeleteAwareStore()
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
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_3",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_3/active.mp4",
                    "checksum_sha256": "c" * 64,
                    "upload_session_id": "up_3",
                }
            )

            status = delete_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_3",
                job_store=repo,
                outbox=outbox,
                object_storage=storage,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
                checkpoint_store=checkpoint_store,
                artifact_store=artifact_store,
                transcript_store=transcript_store,
            )
            self.assertEqual(status, "deleted")
            row = repo.get("tenant-a", "job_3")
            self.assertEqual(row["status"], "deleted")
            self.assertEqual(outbox.list_pending(limit=20), [])
            self.assertEqual(storage.deleted[0], ("tenant-a", "tenant/tenant-a/job_3/"))
            self.assertEqual(checkpoint_store.deleted, [("tenant-a", "job_3")])
            self.assertEqual(artifact_store.deleted, [("tenant-a", "job_3")])
            self.assertEqual(transcript_store.deleted, [("tenant-a", "job_3")])

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

    def test_delete_upload_pending_job_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_5",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "pending.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "upload_pending",
                    "progress": 0,
                }
            )

            status = delete_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_5",
                job_store=repo,
                outbox=SQLiteOutbox(db_path),
                object_storage=_DeleteAwareStorage(),
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )
            self.assertEqual(status, "deleted")
            self.assertEqual(repo.get("tenant-a", "job_5")["status"], "deleted")

    def test_delete_cancel_requested_job_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_6",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "cancel-requested.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "cancel_requested",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_6/cancel-requested.mp4",
                }
            )

            status = delete_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_6",
                job_store=repo,
                outbox=SQLiteOutbox(db_path),
                object_storage=_DeleteAwareStorage(),
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )
            self.assertEqual(status, "deleted")
            self.assertEqual(repo.get("tenant-a", "job_6")["status"], "deleted")

    def test_delete_deleted_job_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_7",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "already-deleted.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                    "retention_months": 6,
                    "status": "completed",
                    "progress": 100,
                    "object_key": "tenant/tenant-a/job_7/already-deleted.mp4",
                }
            )
            storage = _DeleteAwareStorage()
            first = delete_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_7",
                job_store=repo,
                outbox=SQLiteOutbox(db_path),
                object_storage=storage,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )
            second = delete_job(
                tenant_id="tenant-a",
                actor_id="u-1",
                job_id="job_7",
                job_store=repo,
                outbox=SQLiteOutbox(db_path),
                object_storage=storage,
                audit_log=JsonlAuditLog(Path(tmpdir) / "audit.log"),
            )
            self.assertEqual(first, "deleted")
            self.assertEqual(second, "deleted")


if __name__ == "__main__":
    unittest.main()
