import importlib.util
import sqlite3
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

    def test_correction_session_create_preserves_timeline_gaps(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            transcript_repo = InMemoryTranscriptRepository()
            correction_store = SQLiteTranscriptCorrectionStore(db_path)
            transcript_repo.seed(
                tenant_id="tenant-a",
                job_id="job_corr_gap",
                version=1,
                segments=[
                    {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                    {"segment_id": "seg_2", "start": 2.0, "end": 3.5, "speaker": "S2", "text": "B"},
                    {"segment_id": "seg_3", "start": 10.0, "end": 12.0, "speaker": "S1", "text": "C"},
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
                transcript_correction_store=correction_store,
            )
            client = TestClient(app)

            created = client.post(
                "/api/v1/jobs/job_corr_gap/transcript/correction-sessions",
                headers={"Authorization": "Bearer token"},
                json={"base_version": 1, "autosave_enabled": False},
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()
            self.assertEqual(payload["segments"][0]["start"], 0.0)
            self.assertEqual(payload["segments"][0]["end"], 1.0)
            self.assertEqual(payload["segments"][1]["start"], 2.0)
            self.assertEqual(payload["segments"][1]["end"], 3.5)
            self.assertEqual(payload["segments"][2]["start"], 10.0)
            self.assertEqual(payload["segments"][2]["end"], 12.0)

    def test_legacy_session_open_reseeds_and_removes_additive_drift(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE transcript_correction_sessions (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    base_version INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, job_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE transcript_status (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'in_review',
                    is_final INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, job_id)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO transcript_correction_sessions (
                    tenant_id, job_id, session_id, actor_id, base_version, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "tenant-a",
                    "job_corr_legacy",
                    "cs_legacy",
                    "u-1",
                    1,
                    "2026-03-27T00:00:00+00:00",
                    "2026-03-20T00:00:00+00:00",
                ),
            )
            conn.commit()
            conn.close()

            correction_store = SQLiteTranscriptCorrectionStore(db_path)
            transcript_repo = InMemoryTranscriptRepository()
            transcript_repo.seed(
                tenant_id="tenant-a",
                job_id="job_corr_legacy",
                version=2,
                segments=[
                    {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                    {"segment_id": "seg_2", "start": 2.0, "end": 3.0, "speaker": "S2", "text": "B"},
                    {"segment_id": "seg_3", "start": 25.0, "end": 26.0, "speaker": "S1", "text": "C"},
                ],
            )
            correction_store.update_session(
                tenant_id="tenant-a",
                session_id="cs_legacy",
                payload={
                    "session_id": "cs_legacy",
                    "job_id": "job_corr_legacy",
                    "actor_id": "u-1",
                    "base_version": 1,
                    "autosave_enabled": True,
                    "speaker_labels": {},
                    "review_status": "in_review",
                    "is_final": False,
                    "history_index": 0,
                    "history": [
                        {
                            "segments": [
                                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                                {"segment_id": "seg_2", "start": 1.0, "end": 2.0, "speaker": "S2", "text": "B"},
                                {"segment_id": "seg_3", "start": 2.0, "end": 3.0, "speaker": "S1", "text": "C"},
                            ],
                            "summary": None,
                        }
                    ],
                    "updated_at": "2026-03-20T00:00:00+00:00",
                    "created_at": "2026-03-20T00:00:00+00:00",
                },
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
                "/api/v1/jobs/job_corr_legacy/transcript/correction-sessions",
                headers={"Authorization": "Bearer token"},
                json={
                    "base_version": 2,
                    "autosave_enabled": False,
                    "force_reseed_from_transcript": True,
                },
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()
            self.assertEqual(payload["session_id"], "cs_legacy")
            self.assertEqual(payload["history_index"], 0)
            observed = [(item["start"], item["end"]) for item in payload["segments"]]
            self.assertEqual(observed, [(0.0, 1.0), (2.0, 3.0), (25.0, 26.0)])

    def test_transcript_vs_session_timestamps_are_identical_on_create(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            transcript_repo = InMemoryTranscriptRepository()
            correction_store = SQLiteTranscriptCorrectionStore(db_path)
            segments = [
                {"segment_id": "seg_1", "start": 0.125, "end": 1.75, "speaker": "S1", "text": "A"},
                {"segment_id": "seg_2", "start": 4.0, "end": 5.625, "speaker": "S2", "text": "B"},
                {"segment_id": "seg_3", "start": 90.0, "end": 92.25, "speaker": "S1", "text": "C"},
            ]
            transcript_repo.seed(
                tenant_id="tenant-a",
                job_id="job_corr_match",
                version=1,
                segments=segments,
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

            transcript_response = client.get(
                "/api/v1/jobs/job_corr_match/transcript",
                headers={"Authorization": "Bearer token"},
            )
            self.assertEqual(transcript_response.status_code, 200)
            transcript_payload = transcript_response.json()

            created = client.post(
                "/api/v1/jobs/job_corr_match/transcript/correction-sessions",
                headers={"Authorization": "Bearer token"},
                json={"base_version": 1, "autosave_enabled": False},
            )
            self.assertEqual(created.status_code, 200)
            session_payload = created.json()

            transcript_pairs = [(item["start"], item["end"]) for item in transcript_payload["segments"]]
            session_pairs = [(item["start"], item["end"]) for item in session_payload["segments"]]
            self.assertEqual(session_pairs, transcript_pairs)

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
