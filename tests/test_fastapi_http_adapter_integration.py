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


if __name__ == "__main__":
    unittest.main()
