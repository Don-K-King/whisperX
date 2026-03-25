import importlib.util
import tempfile
import unittest
from pathlib import Path

from evodox.jobs.create_service import JobRecord
from evodox.jobs.infrastructure import (
    JsonlAuditLog,
    LocalObjectStorageCatalog,
    LocalPresignUploadSessionFactory,
    SQLiteCompleteUploadIdempotencyStore,
    SQLiteIdempotencyStore,
    SQLiteJobRepository,
    SQLiteOutbox,
)
from evodox.jobs.transcript_service import InMemoryTranscriptRepository
from evodox.jobs.transcript_correction_store import SQLiteTranscriptCorrectionStore
from evodox.web.fastapi_adapter import FastAPIAdapterSettings, create_fastapi_app


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "fastapi not installed in this environment")
class TranscriptCorrectionFastAPIIntegrationTests(unittest.TestCase):
    @staticmethod
    def _claims(*, tenant_id: str = "tenant-a", roles: list[str] | None = None):
        return {
            "sub": "u-1",
            "tenant_id": tenant_id,
            "roles": roles or ["reviewer"],
            "iss": "https://keycloak.prod/realms/evodox",
            "aud": "evodox-api",
            "exp": 2_000_000_000,
            "iat": 1_999_999_000,
            "nbf": 1_999_999_000,
            "now": 1_999_999_500,
        }

    def test_correction_session_roundtrip_and_commit(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            transcript_repo = InMemoryTranscriptRepository()
            correction_store = SQLiteTranscriptCorrectionStore(db_path)
            transcript_repo.seed(
                tenant_id="tenant-a",
                job_id="job_corr_1",
                version=2,
                segments=[
                    {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hallo"}
                ],
                speaker_labels={"S1": "Alice"},
            )

            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(base_url="https://minio.local", bucket="uploads"),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=transcript_repo,
                transcript_correction_store=correction_store,
            )
            client = TestClient(app)

            created = client.post(
                "/api/v1/jobs/job_corr_1/transcript/correction-sessions",
                headers={"Authorization": "Bearer token"},
                json={"base_version": 2, "autosave_enabled": True},
            )
            self.assertEqual(created.status_code, 200)
            session_id = created.json()["session_id"]

            applied = client.post(
                f"/api/v1/jobs/job_corr_1/transcript/correction-sessions/{session_id}/operations",
                headers={"Authorization": "Bearer token"},
                json={
                    "operations": [
                        {
                            "type": "replace_literal",
                            "query": "Hallo",
                            "replace": "Guten Tag",
                        }
                    ]
                },
            )
            self.assertEqual(applied.status_code, 200)

            committed = client.post(
                f"/api/v1/jobs/job_corr_1/transcript/correction-sessions/{session_id}/commit",
                headers={"Authorization": "Bearer token"},
                json={"base_version": 2, "edit_reason": "Korrektur"},
            )
            self.assertEqual(committed.status_code, 200)
            self.assertEqual(committed.json()["version"], 3)

    def test_status_endpoint_returns_503_when_correction_store_missing(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            transcript_repo = InMemoryTranscriptRepository()
            transcript_repo.seed(
                tenant_id="tenant-a",
                job_id="job_corr_2",
                version=1,
                segments=[
                    {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hallo"}
                ],
            )

            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(base_url="https://minio.local", bucket="uploads"),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=transcript_repo,
                transcript_correction_store=None,
            )
            client = TestClient(app)

            status_update = client.patch(
                "/api/v1/jobs/job_corr_2/transcript/status",
                headers={"Authorization": "Bearer token"},
                json={"review_status": "reviewed", "is_final": True},
            )
            self.assertEqual(status_update.status_code, 503)
            self.assertEqual(
                status_update.json().get("detail", {}).get("error_code"),
                "transcript.correction_unavailable",
            )

    def test_get_correction_session_forbidden_for_other_actor_returns_403(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            transcript_repo = InMemoryTranscriptRepository()
            correction_store = SQLiteTranscriptCorrectionStore(db_path)
            transcript_repo.seed(
                tenant_id="tenant-a",
                job_id="job_corr_3",
                version=1,
                segments=[
                    {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hallo"}
                ],
            )

            def token_verifier(token: str):
                actor = token.split(":")[-1]
                claims = self._claims()
                claims["sub"] = actor
                return claims

            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=token_verifier,
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(base_url="https://minio.local", bucket="uploads"),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=transcript_repo,
                transcript_correction_store=correction_store,
            )
            client = TestClient(app)

            created = client.post(
                "/api/v1/jobs/job_corr_3/transcript/correction-sessions",
                headers={"Authorization": "Bearer dev:u-1"},
                json={"base_version": 1, "autosave_enabled": False},
            )
            self.assertEqual(created.status_code, 200)
            session_id = created.json()["session_id"]

            forbidden = client.get(
                f"/api/v1/jobs/job_corr_3/transcript/correction-sessions/{session_id}",
                headers={"Authorization": "Bearer dev:u-2"},
            )
            self.assertEqual(forbidden.status_code, 403)
            self.assertEqual(
                forbidden.json().get("detail", {}).get("error_code"),
                "transcript.correction_session_forbidden",
            )

    def test_status_endpoint_returns_404_for_unknown_job(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            transcript_repo = InMemoryTranscriptRepository()
            correction_store = SQLiteTranscriptCorrectionStore(db_path)

            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(base_url="https://minio.local", bucket="uploads"),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=transcript_repo,
                transcript_correction_store=correction_store,
            )
            client = TestClient(app)

            status_update = client.patch(
                "/api/v1/jobs/missing/transcript/status",
                headers={"Authorization": "Bearer token"},
                json={"review_status": "reviewed", "is_final": True},
            )
            self.assertEqual(status_update.status_code, 404)
            self.assertEqual(
                status_update.json().get("detail", {}).get("error_code"),
                "transcript.not_found",
            )

    def test_media_source_endpoint_returns_tenant_scoped_url(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                JobRecord(
                    job_id="job_media_1",
                    tenant_id="tenant-a",
                    actor_id="u-1",
                    filename="meeting.mp3",
                    content_type="audio/mpeg",
                    size_bytes=123,
                    retention_months=12,
                    upload_session_id="up_1",
                    object_key="tenant/tenant-a/job_media_1/meeting.mp3",
                    checksum_sha256="a" * 64,
                    status="completed",
                )
            )

            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(base_url="https://minio.local", bucket="uploads"),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=InMemoryTranscriptRepository(),
                transcript_correction_store=SQLiteTranscriptCorrectionStore(db_path),
                media_base_url="https://minio.local",
                media_bucket="uploads",
            )
            client = TestClient(app)

            response = client.get(
                "/api/v1/jobs/job_media_1/media-source",
                headers={"Authorization": "Bearer token"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json().get("media_url"),
                "https://minio.local/uploads/tenant/tenant-a/job_media_1/meeting.mp3",
            )

    def test_media_source_endpoint_returns_404_and_503_paths(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                JobRecord(
                    job_id="job_media_2",
                    tenant_id="tenant-a",
                    actor_id="u-1",
                    filename="meeting.mp3",
                    content_type="audio/mpeg",
                    size_bytes=123,
                    retention_months=12,
                    upload_session_id=None,
                    object_key=None,
                    checksum_sha256=None,
                    status="completed",
                )
            )

            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(),
                job_repository=repo,
                upload_session_factory=LocalPresignUploadSessionFactory(base_url="https://minio.local", bucket="uploads"),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=InMemoryTranscriptRepository(),
                transcript_correction_store=SQLiteTranscriptCorrectionStore(db_path),
                media_base_url="https://minio.local",
                media_bucket="uploads",
            )
            client = TestClient(app)

            missing = client.get(
                "/api/v1/jobs/unknown/media-source",
                headers={"Authorization": "Bearer token"},
            )
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json().get("detail", {}).get("error_code"), "job.not_found")

            unavailable = client.get(
                "/api/v1/jobs/job_media_2/media-source",
                headers={"Authorization": "Bearer token"},
            )
            self.assertEqual(unavailable.status_code, 503)
            self.assertEqual(unavailable.json().get("detail", {}).get("error_code"), "media_source.unavailable")


if __name__ == "__main__":
    unittest.main()
