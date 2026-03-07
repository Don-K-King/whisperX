import json
import tempfile
import unittest
from pathlib import Path

from evodox.jobs.create_service import CreateJobResponse, IdempotencyRecord, UploadSession
from evodox.jobs.infrastructure import (
    JsonlAuditLog,
    LocalPresignUploadSessionFactory,
    SQLiteIdempotencyStore,
    SQLiteJobRepository,
)


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


if __name__ == "__main__":
    unittest.main()
