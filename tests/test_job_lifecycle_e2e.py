import tempfile
import unittest
from pathlib import Path

from evodox.jobs.complete_upload_service import (
    CompleteUploadInput,
    QueueSelectionPolicy,
    complete_upload,
)
from evodox.jobs.create_service import ActorContext, CreateJobInput, create_job
from evodox.jobs.get_job_status_service import get_job_status
from evodox.jobs.infrastructure import (
    InMemoryQueuePublisher,
    JsonlAuditLog,
    LocalObjectStorageCatalog,
    LocalPresignUploadSessionFactory,
    OutboxQueueDispatcher,
    SQLiteCompleteUploadIdempotencyStore,
    SQLiteIdempotencyStore,
    SQLiteJobRepository,
    SQLiteOutbox,
)


class JobLifecycleE2ETests(unittest.TestCase):
    def test_create_complete_dispatch_and_status_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repository = SQLiteJobRepository(db_path)
            object_storage = LocalObjectStorageCatalog()
            outbox = SQLiteOutbox(db_path)

            created = create_job(
                CreateJobInput(
                    filename="hearing.mp4",
                    content_type="video/mp4",
                    size_bytes=123_456,
                    retention_months=6,
                    idempotency_key="create-e2e-0001",
                ),
                actor_context=ActorContext(actor_id="u-1", tenant_id="tenant-a"),
                job_repository=repository,
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local",
                    bucket="uploads",
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
            )

            object_storage.register_object(
                object_key=created.upload.object_key,
                checksum_sha256="a" * 64,
            )

            completed = complete_upload(
                CompleteUploadInput(
                    job_id=created.job_id,
                    upload_session_id=created.upload.session_id,
                    object_key=created.upload.object_key,
                    checksum_sha256="a" * 64,
                    idempotency_key="complete-e2e-0001",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                job_store=repository,
                object_storage=object_storage,
                outbox=outbox,
                idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                queue_policy=QueueSelectionPolicy(),
            )

            self.assertEqual(completed.status, "queued")
            self.assertEqual(completed.queue, "gpu-standard")

            publisher = InMemoryQueuePublisher()
            dispatched_count = OutboxQueueDispatcher(outbox=outbox, queue_publisher=publisher).dispatch_pending(limit=10)

            self.assertEqual(dispatched_count, 1)
            self.assertEqual(len(publisher.messages), 1)
            queue_name, message = publisher.messages[0]
            self.assertEqual(queue_name, "gpu-standard")
            self.assertEqual(message["job_id"], created.job_id)
            self.assertEqual(message["tenant_id"], "tenant-a")

            status = get_job_status(job_id=created.job_id, tenant_id="tenant-a", job_store=repository)
            self.assertEqual(status.status, "queued")
            self.assertEqual(status.progress, 0)


if __name__ == "__main__":
    unittest.main()
