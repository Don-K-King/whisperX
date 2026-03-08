import json
import sqlite3
import sys
import tempfile
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from evodox.jobs.create_service import CreateJobResponse, IdempotencyRecord, UploadSession
from evodox.jobs.infrastructure import (
    InMemoryRetentionObjectStorage,
    JsonlAuditLog,
    LocalPresignUploadSessionFactory,
    RabbitMQQueuePublisher,
    RetryablePublishError,
    SQLiteIdempotencyStore,
    SQLiteJobRepository,
    SQLiteOutbox,
    SQLiteRetentionCandidateRepository,
    SQLiteRetentionExecutionRepository,
    SQLiteRetentionRetryStore,
    SQLiteSchedulerLeaseStore,
)
from evodox.jobs.retention_scheduler import RetentionFailureRecord


class InfrastructureAdaptersTests(unittest.TestCase):
    def test_sqlite_job_repository_persists_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.mp3",
                    "content_type": "audio/mpeg",
                    "size_bytes": 12,
                    "retention_months": 6,
                    "status": "upload_pending",
                }
            )

            rows = repo.list_for_tenant("tenant-a")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["job_id"], "job_1")

    def test_sqlite_idempotency_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            store = SQLiteIdempotencyStore(db_path)
            response = CreateJobResponse(
                job_id="job_22",
                tenant_id="tenant-a",
                status="upload_pending",
                upload=UploadSession(
                    session_id="up_22",
                    object_key="tenant/tenant-a/job_22/audio.mp3",
                    presigned_url="https://example/upload",
                    expires_at="2030-01-01T00:00:00+00:00",
                ),
            )
            store.put(
                "tenant-a",
                "idem-1",
                IdempotencyRecord(tenant_id="tenant-a", payload_hash="abc", response=response),
            )

            saved = store.get("tenant-a", "idem-1")
            assert saved is not None
            self.assertEqual(saved.payload_hash, "abc")
            self.assertEqual(saved.response.job_id, "job_22")

    def test_local_presign_factory_generates_tenant_scoped_key(self):
        factory = LocalPresignUploadSessionFactory(
            base_url="https://minio.local",
            bucket="uploads",
        )
        session = factory.create_session(tenant_id="tenant-a", job_id="job_9", filename="file.mp4")
        self.assertIn("tenant/tenant-a/job_9/file.mp4", session.object_key)
        self.assertIn("signature=", session.presigned_url)

    def test_jsonl_audit_log_appends_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.log"
            audit = JsonlAuditLog(log_path)
            audit.append({"action": "job.create", "tenant_id": "tenant-a"})

            lines = log_path.read_text().strip().splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["action"], "job.create")

    def test_rabbitmq_publisher_maps_broker_failure_to_retryable_error(self):
        publisher = RabbitMQQueuePublisher(amqp_url="amqp://guest:guest@localhost:5672/%2F")
        fake_pika = SimpleNamespace(
            URLParameters=lambda url: url,
            BasicProperties=lambda **kwargs: kwargs,
            BlockingConnection=lambda params: (_ for _ in ()).throw(RuntimeError(f"cannot connect {params}")),
        )
        previous = sys.modules.get("pika")
        sys.modules["pika"] = fake_pika
        try:
            with self.assertRaises(RetryablePublishError) as ctx:
                publisher.publish(
                    "gpu-standard",
                    {"event_type": "job.queued"},
                    message_id="evt_1",
                    headers={"tenant_id": "tenant-a"},
                )
            self.assertEqual(ctx.exception.error_code, "broker.unavailable")
        finally:
            if previous is not None:
                sys.modules["pika"] = previous
            else:
                del sys.modules["pika"]


    def test_retention_candidate_repo_is_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            job_repo = SQLiteJobRepository(db_path)
            job_repo.create(
                {
                    "job_id": "job_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.mp3",
                    "content_type": "audio/mpeg",
                    "size_bytes": 12,
                    "retention_months": 1,
                    "status": "completed",
                }
            )
            job_repo.create(
                {
                    "job_id": "job_2",
                    "tenant_id": "tenant-b",
                    "actor_id": "u-2",
                    "filename": "audio2.mp3",
                    "content_type": "audio/mpeg",
                    "size_bytes": 12,
                    "retention_months": 1,
                    "status": "completed",
                }
            )

            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE jobs SET created_at = '2020-01-01T00:00:00+00:00'")

            repo = SQLiteRetentionCandidateRepository(db_path)
            due = repo.list_due_for_tenant(tenant_id="tenant-a", now=datetime(2026, 1, 1, tzinfo=timezone.utc), limit=100)

            self.assertEqual(len(due), 1)
            self.assertEqual(due[0].tenant_id, "tenant-a")
            self.assertEqual(due[0].job_id, "job_1")

    def test_retention_execution_repo_marks_deleted_and_prunes_outbox_for_tenant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            job_repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            job_repo.create(
                {
                    "job_id": "job_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.mp3",
                    "content_type": "audio/mpeg",
                    "size_bytes": 12,
                    "retention_months": 1,
                    "status": "completed",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_1",
                    "queue": "gpu-standard",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-b",
                    "job_id": "job_1",
                    "queue": "gpu-standard",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
            )

            storage = InMemoryRetentionObjectStorage()
            repo = SQLiteRetentionExecutionRepository(db_path, object_storage=storage)
            ok = repo.delete_storage(tenant_id="tenant-a", job_id="job_1")
            marked = repo.mark_deleted(
                tenant_id="tenant-a",
                job_id="job_1",
                deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

            self.assertTrue(ok)
            self.assertTrue(marked)
            row = job_repo.get("tenant-a", "job_1")
            self.assertEqual(row["status"], "deleted")
            self.assertEqual(row["filename"], "[redacted]")
            self.assertEqual(storage.deleted_prefixes[0], ("tenant-a", "tenant/tenant-a/job_1/"))
            dlq_rows = outbox.list_pending(limit=10)
            self.assertEqual(len(dlq_rows), 1)
            self.assertEqual(dlq_rows[0]["tenant_id"], "tenant-b")

    def test_scheduler_lease_store_persists_last_run_and_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            lease_a = SQLiteSchedulerLeaseStore(db_path, lock_owner="owner-a")
            lease_b = SQLiteSchedulerLeaseStore(db_path, lock_owner="owner-b")
            now = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)

            self.assertTrue(lease_a.should_run(now=now, interval=timedelta(minutes=1)))
            self.assertFalse(lease_b.should_run(now=now, interval=timedelta(minutes=1)))
            lease_a.mark_ran(now=now)
            self.assertFalse(lease_b.should_run(now=now + timedelta(seconds=5), interval=timedelta(minutes=1)))
            self.assertFalse(lease_b.renew_lock(now=now + timedelta(seconds=5)))
            self.assertFalse(lease_a.renew_lock(now=now + timedelta(seconds=5)))
            self.assertTrue(lease_b.should_run(now=now + timedelta(minutes=2), interval=timedelta(minutes=1)))

    def test_retention_retry_store_enforces_idempotency_and_due_indexing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            store = SQLiteRetentionRetryStore(db_path)
            now = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            record = RetentionFailureRecord(
                failure_id="f-1",
                tenant_id="tenant-a",
                job_id="job-1",
                failure_class="db_mark_failed",
                first_failed_at=now - timedelta(minutes=10),
                next_attempt_at=now - timedelta(minutes=1),
                attempts=0,
            )

            store.upsert_failure(record)
            store.upsert_failure(record)
            due = store.list_due(now=now, limit=10)

            self.assertEqual(len(due), 1)
            store.mark_retry_scheduled("f-1", failure_class="db_mark_failed", next_attempt_at=now + timedelta(minutes=5))
            pending_early = store.list_due(now=now + timedelta(minutes=2), limit=10)
            self.assertEqual(pending_early, [])
            pending_late = store.list_due(now=now + timedelta(minutes=6), limit=10)
            self.assertEqual(len(pending_late), 1)
            store.mark_invalid("f-1", failure_class="db_mark_failed", reason="invalid.retry_record")
            self.assertEqual(store.list_due(now=now + timedelta(minutes=7), limit=10), [])
            store.mark_recovered("f-1", failure_class="db_mark_failed")
            self.assertEqual(store.list_due(now=now + timedelta(minutes=7), limit=10), [])

            with sqlite3.connect(db_path) as conn:
                invalid_reason = conn.execute(
                    "SELECT invalid_reason FROM retention_retry_queue WHERE failure_id = ? AND failure_class = ?",
                    ("f-1", "db_mark_failed"),
                ).fetchone()[0]
            self.assertIsNone(invalid_reason)

            with sqlite3.connect(db_path) as conn:
                idx_names = {row[1] for row in conn.execute("PRAGMA index_list(retention_retry_queue)").fetchall()}
            self.assertIn("idx_retention_retry_tenant_id", idx_names)
            self.assertIn("idx_retention_retry_status_due", idx_names)
            self.assertIn("idx_retention_retry_next_attempt_at", idx_names)


if __name__ == "__main__":
    unittest.main()
