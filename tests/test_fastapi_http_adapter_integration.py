import importlib.util
import unittest

from evodox.jobs.infrastructure import (
    JsonlAuditLog,
    LocalObjectStorageCatalog,
    LocalPresignUploadSessionFactory,
    SQLiteCompleteUploadIdempotencyStore,
    SQLiteIdempotencyStore,
    SQLiteJobRepository,
    SQLiteOutbox,
)
from evodox.web.fastapi_adapter import FastAPIAdapterSettings, create_fastapi_app


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "fastapi not installed in this environment")
class FastAPIAdapterIntegrationTests(unittest.TestCase):
    @staticmethod
    def _claims(*, tenant_id: str = "tenant-a", roles: list[str] | None = None):
        return {
            "sub": "u-1",
            "tenant_id": tenant_id,
            "roles": roles or ["user"],
            "iss": "https://keycloak.prod/realms/evodox",
            "aud": "evodox-api",
            "exp": 2_000_000_000,
            "iat": 1_999_999_000,
            "nbf": 1_999_999_000,
            "now": 1_999_999_500,
        }

    def test_post_jobs_happy_path(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)
            response = client.post(
                "/api/v1/jobs",
                headers={
                    "Authorization": "Bearer token",
                    "Idempotency-Key": "idempotent-1234",
                },
                json={
                    "filename": "hearing.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["tenant_id"], "tenant-a")


    def test_get_job_status_happy_path(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_status_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "hearing.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                    "status": "processing",
                }
            )
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)
            response = client.get(
                "/api/v1/jobs/job_status_1",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["job_id"], "job_status_1")
            self.assertEqual(response.json()["status"], "processing")

    def test_get_jobs_returns_tenant_scoped_list(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "a.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 123,
                    "retention_months": 6,
                    "status": "queued",
                }
            )
            repo.create(
                {
                    "job_id": "job_2",
                    "tenant_id": "tenant-b",
                    "actor_id": "u-2",
                    "filename": "b.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 123,
                    "retention_months": 6,
                    "status": "queued",
                }
            )
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(tenant_id="tenant-a"),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)
            response = client.get("/api/v1/jobs", headers={"Authorization": "Bearer token"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["jobs"]), 1)
            self.assertEqual(response.json()["jobs"][0]["job_id"], "job_1")

    def test_get_audit_requires_admin_role(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            audit = JsonlAuditLog(Path(tmp) / "audit.log")
            audit.append({"action": "job.create", "tenant_id": "tenant-a", "actor_id": "u-1"})
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(roles=["user"]),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=audit,
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)
            response = client.get("/api/v1/audit", headers={"Authorization": "Bearer token"})

            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"]["error_code"], "authz.deny")

    def test_get_audit_returns_tenant_scoped_events_for_admin(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            audit = JsonlAuditLog(Path(tmp) / "audit.log")
            audit.append({"action": "job.create", "tenant_id": "tenant-a", "actor_id": "u-1"})
            audit.append({"action": "job.create", "tenant_id": "tenant-b", "actor_id": "u-2"})
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(roles=["admin"], tenant_id="tenant-a"),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=audit,
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)
            response = client.get("/api/v1/audit", headers={"Authorization": "Bearer token"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["events"]), 1)
            self.assertEqual(response.json()["events"][0]["tenant_id"], "tenant-a")

    def test_pause_queued_job_transitions_to_paused(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_pause_queued",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "queued.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                    "status": "queued",
                    "progress": 5,
                    "object_key": "tenant/tenant-a/job_pause_queued/queued.mp4",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_pause_queued",
                }
            )
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(tenant_id="tenant-a"),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)

            response = client.post(
                "/api/v1/jobs/job_pause_queued/pause",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "paused")
            self.assertEqual(response.json()["progress"], 5)
            row = repo.get("tenant-a", "job_pause_queued")
            self.assertEqual(row["status"], "paused")

    def test_resume_paused_job_is_idempotent_and_queues_once(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_resume_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "resume.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 4321,
                    "retention_months": 6,
                    "status": "paused",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_resume_1/resume.mp4",
                    "checksum_sha256": "b" * 64,
                    "upload_session_id": "up_resume_1",
                }
            )
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(tenant_id="tenant-a"),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=outbox,
            )
            client = TestClient(app)

            first = client.post(
                "/api/v1/jobs/job_resume_1/resume",
                headers={"Authorization": "Bearer token"},
            )
            second = client.post(
                "/api/v1/jobs/job_resume_1/resume",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(first.json()["status"], "queued")
            self.assertEqual(second.json()["status"], "queued")
            pending = outbox.list_pending(limit=50)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["job_id"], "job_resume_1")

    def test_delete_completed_job_soft_deletes_and_hides_from_list(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_delete_ok",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "done.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                    "status": "completed",
                    "progress": 100,
                    "object_key": "tenant/tenant-a/job_delete_ok/done.mp4",
                    "checksum_sha256": "c" * 64,
                    "upload_session_id": "up_delete_ok",
                }
            )
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(tenant_id="tenant-a"),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)

            delete_response = client.delete(
                "/api/v1/jobs/job_delete_ok",
                headers={"Authorization": "Bearer token"},
            )
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["status"], "deleted")
            row = repo.get("tenant-a", "job_delete_ok")
            self.assertEqual(row["status"], "deleted")
            self.assertTrue(row["deleted_at"])

            jobs_response = client.get("/api/v1/jobs", headers={"Authorization": "Bearer token"})
            self.assertEqual(jobs_response.status_code, 200)
            self.assertEqual(jobs_response.json()["jobs"], [])

    def test_delete_active_job_returns_conflict(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_delete_conflict",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "running.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                    "status": "processing",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_delete_conflict/running.mp4",
                    "checksum_sha256": "d" * 64,
                    "upload_session_id": "up_delete_conflict",
                }
            )
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(tenant_id="tenant-a"),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
            )
            client = TestClient(app)

            response = client.delete(
                "/api/v1/jobs/job_delete_conflict",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"]["error_code"], "job.delete.active_conflict")


if __name__ == "__main__":
    unittest.main()
