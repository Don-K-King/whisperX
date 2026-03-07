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
                token_verifier=lambda _token: {
                    "sub": "u-1",
                    "tenant_id": "tenant-a",
                    "roles": ["user"],
                    "iss": "https://keycloak.prod/realms/evodox",
                    "aud": "evodox-api",
                    "exp": 2_000_000_000,
                    "iat": 1_999_999_000,
                    "nbf": 1_999_999_000,
                    "now": 1_999_999_500,
                },
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
                token_verifier=lambda _token: {
                    "sub": "u-1",
                    "tenant_id": "tenant-a",
                    "roles": ["user"],
                    "iss": "https://keycloak.prod/realms/evodox",
                    "aud": "evodox-api",
                    "exp": 2_000_000_000,
                    "iat": 1_999_999_000,
                    "nbf": 1_999_999_000,
                    "now": 1_999_999_500,
                },
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


if __name__ == "__main__":
    unittest.main()
