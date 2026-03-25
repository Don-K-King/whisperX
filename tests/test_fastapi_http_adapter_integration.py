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
    SQLiteTranscriptRepository,
    SQLiteTenantTranscriptionSettingsStore,
    SQLiteWorkerArtifactStore,
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
            repo = SQLiteJobRepository(db_path)
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
            created = repo.get("tenant-a", response.json()["job_id"])
            self.assertIsNotNone(created)
            self.assertIn('"language": "de"', str(created.get("transcription_options_json")))

    def test_post_jobs_accepts_explicit_language(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
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
            response = client.post(
                "/api/v1/jobs",
                headers={
                    "Authorization": "Bearer token",
                    "Idempotency-Key": "idempotent-1235",
                },
                json={
                    "filename": "hearing.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                    "language": "en",
                },
            )

            self.assertEqual(response.status_code, 200)
            created = repo.get("tenant-a", response.json()["job_id"])
            self.assertIsNotNone(created)
            self.assertIn('"language": "en"', str(created.get("transcription_options_json")))


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

    def test_get_transcription_settings_requires_admin_role(self):
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
                token_verifier=lambda _token: self._claims(roles=["user"]),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcription_settings_store=SQLiteTenantTranscriptionSettingsStore(db_path),
            )
            client = TestClient(app)
            response = client.get("/api/v1/admin/transcription-settings", headers={"Authorization": "Bearer token"})

            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"]["error_code"], "authz.deny")

    def test_get_transcription_settings_returns_defaults_for_admin(self):
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
                token_verifier=lambda _token: self._claims(roles=["admin"], tenant_id="tenant-a"),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcription_settings_store=SQLiteTenantTranscriptionSettingsStore(db_path),
            )
            client = TestClient(app)
            response = client.get("/api/v1/admin/transcription-settings", headers={"Authorization": "Bearer token"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["tenant_id"], "tenant-a")
            self.assertEqual(payload["decoding_options"]["beam_size"], 5)
            self.assertEqual(payload["decoding_options"]["temperature"], 0.0)

    def test_put_transcription_settings_roundtrip_for_admin(self):
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
                token_verifier=lambda _token: self._claims(roles=["admin"], tenant_id="tenant-a"),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcription_settings_store=SQLiteTenantTranscriptionSettingsStore(db_path),
            )
            client = TestClient(app)

            update = client.put(
                "/api/v1/admin/transcription-settings",
                headers={"Authorization": "Bearer token"},
                json={
                    "temperature": 0.2,
                    "beam_size": 4,
                    "patience": 1.1,
                    "length_penalty": 1.0,
                    "compression_ratio_threshold": 2.2,
                    "logprob_threshold": -1.0,
                    "no_speech_threshold": 0.5,
                    "suppress_tokens": "-1,12",
                    "initial_prompt": "Bitte juristische Begriffe korrekt transkribieren.",
                    "condition_on_previous_text": True,
                },
            )
            self.assertEqual(update.status_code, 200)
            self.assertEqual(update.json()["decoding_options"]["beam_size"], 4)

            fetched = client.get("/api/v1/admin/transcription-settings", headers={"Authorization": "Bearer token"})
            self.assertEqual(fetched.status_code, 200)
            self.assertEqual(fetched.json()["decoding_options"]["beam_size"], 4)
            self.assertEqual(fetched.json()["decoding_options"]["condition_on_previous_text"], True)

    def test_put_transcription_settings_rejects_invalid_payload(self):
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
                token_verifier=lambda _token: self._claims(roles=["admin"], tenant_id="tenant-a"),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcription_settings_store=SQLiteTenantTranscriptionSettingsStore(db_path),
            )
            client = TestClient(app)

            response = client.put(
                "/api/v1/admin/transcription-settings",
                headers={"Authorization": "Bearer token"},
                json={"temperature": 9.9},
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"]["error_code"], "transcription_settings.invalid_payload")

    def test_put_transcript_speaker_labels_creates_new_transcript_version(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            worker_artifacts = SQLiteWorkerArtifactStore(db_path)
            worker_artifacts.put_transcript(
                tenant_id="tenant-a",
                job_id="job_transcript_alias_1",
                artifact={
                    "transcript": {"segments": [{"start": 0.0, "end": 1.0, "text": "Hallo"}]},
                    "diarization": {"segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0}]},
                },
            )
            transcript_repo = SQLiteTranscriptRepository(db_path)
            current = transcript_repo.get_current("tenant-a", "job_transcript_alias_1")
            assert current is not None
            self.assertEqual(current.version, 1)

            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(roles=["user"], tenant_id="tenant-a"),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=transcript_repo,
            )
            client = TestClient(app)

            response = client.put(
                "/api/v1/jobs/job_transcript_alias_1/transcript/speaker-labels",
                headers={"Authorization": "Bearer token"},
                json={
                    "base_version": 1,
                    "speaker_labels": {"SPEAKER_01": "Patrick"},
                    "edit_reason": "Speaker labels",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["version"], 2)

            transcript = client.get(
                "/api/v1/jobs/job_transcript_alias_1/transcript",
                headers={"Authorization": "Bearer token"},
            )
            self.assertEqual(transcript.status_code, 200)
            self.assertEqual(transcript.json()["version"], 2)
            self.assertEqual(transcript.json()["speaker_labels"]["SPEAKER_01"], "Patrick")

    def test_put_transcript_speaker_labels_is_tenant_scoped(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            worker_artifacts = SQLiteWorkerArtifactStore(db_path)
            worker_artifacts.put_transcript(
                tenant_id="tenant-a",
                job_id="job_transcript_alias_2",
                artifact={
                    "transcript": {"segments": [{"start": 0.0, "end": 1.0, "text": "Hallo"}]},
                    "diarization": {"segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0}]},
                },
            )
            transcript_repo = SQLiteTranscriptRepository(db_path)
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(roles=["user"], tenant_id="tenant-b"),
                job_repository=SQLiteJobRepository(db_path),
                upload_session_factory=LocalPresignUploadSessionFactory(
                    base_url="https://minio.local", bucket="uploads"
                ),
                audit_log=JsonlAuditLog(Path(tmp) / "audit.log"),
                idempotency_store=SQLiteIdempotencyStore(db_path),
                complete_upload_idempotency_store=SQLiteCompleteUploadIdempotencyStore(db_path),
                object_storage=LocalObjectStorageCatalog(),
                outbox=SQLiteOutbox(db_path),
                transcript_repository=transcript_repo,
            )
            client = TestClient(app)

            response = client.put(
                "/api/v1/jobs/job_transcript_alias_2/transcript/speaker-labels",
                headers={"Authorization": "Bearer token"},
                json={
                    "base_version": 1,
                    "speaker_labels": {"SPEAKER_01": "Patrick"},
                    "edit_reason": "Speaker labels",
                },
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"]["error_code"], "transcript.not_found")

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

    def test_cancel_paused_job_is_idempotent_and_terminal(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_cancel_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "paused.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 4321,
                    "retention_months": 6,
                    "status": "paused",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_cancel_1/paused.mp4",
                    "checksum_sha256": "c" * 64,
                    "upload_session_id": "up_cancel_1",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_cancel_1",
                    "queue": "gpu-standard",
                    "upload_session_id": "up_cancel_1",
                    "object_key": "tenant/tenant-a/job_cancel_1/paused.mp4",
                    "checksum_sha256": "c" * 64,
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
                "/api/v1/jobs/job_cancel_1/cancel",
                headers={"Authorization": "Bearer token"},
            )
            second = client.post(
                "/api/v1/jobs/job_cancel_1/cancel",
                headers={"Authorization": "Bearer token"},
            )
            resumed = client.post(
                "/api/v1/jobs/job_cancel_1/resume",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(first.json()["status"], "canceled")
            self.assertEqual(second.json()["status"], "canceled")
            self.assertEqual(outbox.list_pending(limit=20), [])
            self.assertEqual(resumed.status_code, 409)
            self.assertEqual(resumed.json()["detail"]["error_code"], "job.resume.invalid_state")

    def test_cancel_processing_job_sets_cancel_requested(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_cancel_2",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "running.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                    "status": "processing",
                    "progress": 41,
                    "object_key": "tenant/tenant-a/job_cancel_2/running.mp4",
                    "checksum_sha256": "d" * 64,
                    "upload_session_id": "up_cancel_2",
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
                "/api/v1/jobs/job_cancel_2/cancel",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "cancel_requested")
            self.assertEqual(repo.get("tenant-a", "job_cancel_2")["status"], "cancel_requested")

    def test_cancel_is_tenant_scoped(self):
        from fastapi.testclient import TestClient
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_cancel_scope",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "running.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1234,
                    "retention_months": 6,
                    "status": "paused",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_cancel_scope/running.mp4",
                    "checksum_sha256": "e" * 64,
                    "upload_session_id": "up_cancel_scope",
                }
            )
            app = create_fastapi_app(
                settings=FastAPIAdapterSettings(
                    expected_issuer="https://keycloak.prod/realms/evodox",
                    expected_audience="evodox-api",
                ),
                token_verifier=lambda _token: self._claims(tenant_id="tenant-b"),
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
                "/api/v1/jobs/job_cancel_scope/cancel",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"]["error_code"], "job.not_found")

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

    def test_delete_active_job_force_soft_deletes(self):
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
            outbox = SQLiteOutbox(db_path)
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_delete_conflict",
                    "queue": "cpu-short",
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
                outbox=outbox,
            )
            client = TestClient(app)

            response = client.delete(
                "/api/v1/jobs/job_delete_conflict",
                headers={"Authorization": "Bearer token"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "deleted")
            row = repo.get("tenant-a", "job_delete_conflict")
            self.assertEqual(row["status"], "deleted")
            self.assertEqual(outbox.list_pending(limit=20), [])


if __name__ == "__main__":
    unittest.main()
