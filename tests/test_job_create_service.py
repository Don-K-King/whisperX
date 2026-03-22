import unittest
from dataclasses import dataclass

from evodox.jobs.create_service import (
    ALLOWED_UPLOAD_CONTENT_TYPES,
    CreateJobInput,
    InMemoryAuditLog,
    InMemoryIdempotencyStore,
    InMemoryJobRepository,
    InMemoryUploadSessionFactory,
    ValidationError,
    create_job,
)


@dataclass(frozen=True)
class _ActorContext:
    actor_id: str = "u-1001"
    tenant_id: str = "tenant-a"


class CreateJobValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = _ActorContext()

    def test_rejects_unsupported_content_type(self):
        with self.assertRaises(ValidationError) as exc_info:
            create_job(
                CreateJobInput(
                    filename="audio.exe",
                    content_type="application/octet-stream",
                    size_bytes=10,
                    retention_months=12,
                    idempotency_key="idemp-1",
                ),
                actor_context=self.ctx,
                job_repository=InMemoryJobRepository(),
                upload_session_factory=InMemoryUploadSessionFactory(),
                audit_log=InMemoryAuditLog(),
                idempotency_store=InMemoryIdempotencyStore(),
            )

        self.assertEqual(exc_info.exception.error_code, "job.validation.content_type")

    def test_rejects_oversized_upload(self):
        with self.assertRaises(ValidationError) as exc_info:
            create_job(
                CreateJobInput(
                    filename="large.mp4",
                    content_type="video/mp4",
                    size_bytes=21_474_836_481,
                    retention_months=12,
                    idempotency_key="idemp-2",
                ),
                actor_context=self.ctx,
                job_repository=InMemoryJobRepository(),
                upload_session_factory=InMemoryUploadSessionFactory(),
                audit_log=InMemoryAuditLog(),
                idempotency_store=InMemoryIdempotencyStore(),
            )

        self.assertEqual(exc_info.exception.error_code, "job.validation.size")

    def test_rejects_invalid_retention_range(self):
        with self.assertRaises(ValidationError) as exc_info:
            create_job(
                CreateJobInput(
                    filename="audio.mp3",
                    content_type="audio/mpeg",
                    size_bytes=4096,
                    retention_months=99,
                    idempotency_key="idemp-3",
                ),
                actor_context=self.ctx,
                job_repository=InMemoryJobRepository(),
                upload_session_factory=InMemoryUploadSessionFactory(),
                audit_log=InMemoryAuditLog(),
                idempotency_store=InMemoryIdempotencyStore(),
            )

        self.assertEqual(exc_info.exception.error_code, "job.validation.retention")

    def test_rejects_filename_with_control_characters(self):
        with self.assertRaises(ValidationError) as exc_info:
            create_job(
                CreateJobInput(
                    filename="unsafe\x00name.mp4",
                    content_type="video/mp4",
                    size_bytes=2048,
                    retention_months=12,
                    idempotency_key="idemp-4",
                ),
                actor_context=self.ctx,
                job_repository=InMemoryJobRepository(),
                upload_session_factory=InMemoryUploadSessionFactory(),
                audit_log=InMemoryAuditLog(),
                idempotency_store=InMemoryIdempotencyStore(),
            )

        self.assertEqual(exc_info.exception.error_code, "job.validation.filename")


class CreateJobIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = _ActorContext()
        self.repo = InMemoryJobRepository()
        self.sessions = InMemoryUploadSessionFactory()
        self.audit = InMemoryAuditLog()
        self.idempotency = InMemoryIdempotencyStore()

    def test_creates_tenant_scoped_job_and_audit_event(self):
        response = create_job(
            CreateJobInput(
                filename="hearing-01.mp4",
                content_type="video/mp4",
                size_bytes=1024,
                retention_months=12,
                idempotency_key="idemp-ok",
            ),
            actor_context=self.ctx,
            job_repository=self.repo,
            upload_session_factory=self.sessions,
            audit_log=self.audit,
            idempotency_store=self.idempotency,
        )

        self.assertEqual(response.tenant_id, "tenant-a")
        self.assertEqual(response.status, "upload_pending")
        self.assertTrue(response.upload.session_id.startswith("up_"))
        self.assertEqual(len(self.repo.jobs), 1)
        self.assertEqual(self.repo.jobs[0].tenant_id, "tenant-a")
        self.assertEqual(len(self.audit.events), 1)
        self.assertEqual(self.audit.events[0]["action"], "job.create")

    def test_idempotency_key_returns_same_job_without_duplicates(self):
        request = CreateJobInput(
            filename="hearing-02.mp4",
            content_type="video/mp4",
            size_bytes=2048,
            retention_months=6,
            idempotency_key="idemp-same",
        )

        first = create_job(
            request,
            actor_context=self.ctx,
            job_repository=self.repo,
            upload_session_factory=self.sessions,
            audit_log=self.audit,
            idempotency_store=self.idempotency,
        )
        second = create_job(
            request,
            actor_context=self.ctx,
            job_repository=self.repo,
            upload_session_factory=self.sessions,
            audit_log=self.audit,
            idempotency_store=self.idempotency,
        )

        self.assertEqual(first.job_id, second.job_id)
        self.assertEqual(first.upload.session_id, second.upload.session_id)
        self.assertEqual(len(self.repo.jobs), 1)
        self.assertEqual(len(self.audit.events), 1)

    def test_idempotency_key_conflict_on_payload_mismatch(self):
        create_job(
            CreateJobInput(
                filename="a.mp3",
                content_type="audio/mpeg",
                size_bytes=10,
                retention_months=3,
                idempotency_key="idemp-conflict",
            ),
            actor_context=self.ctx,
            job_repository=self.repo,
            upload_session_factory=self.sessions,
            audit_log=self.audit,
            idempotency_store=self.idempotency,
        )

        with self.assertRaises(ValidationError) as exc_info:
            create_job(
                CreateJobInput(
                    filename="b.mp3",
                    content_type="audio/mpeg",
                    size_bytes=11,
                    retention_months=3,
                    idempotency_key="idemp-conflict",
                ),
                actor_context=self.ctx,
                job_repository=self.repo,
                upload_session_factory=self.sessions,
                audit_log=self.audit,
                idempotency_store=self.idempotency,
            )

        self.assertEqual(exc_info.exception.error_code, "job.idempotency.conflict")


if __name__ == "__main__":
    unittest.main()
