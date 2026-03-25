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
    SQLiteJobCheckpointStore,
    SQLiteJobRepository,
    SQLiteOutbox,
    SQLiteRetentionCandidateRepository,
    SQLiteRetentionExecutionRepository,
    SQLiteRetentionRetryStore,
    SQLiteSchedulerLeaseStore,
    SQLiteTenantTranscriptionSettingsStore,
    SQLiteTranscriptRepository,
    SQLiteWorkerArtifactStore,
)
from evodox.jobs.transcript_service import TranscriptConflictError
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

    def test_sqlite_job_checkpoint_store_upserts_stage_and_segment_offset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            store = SQLiteJobCheckpointStore(db_path)
            store.upsert(
                tenant_id="tenant-a",
                job_id="job_cp_1",
                stage="asr_started",
                stage_offset=3,
                payload={"segments_done": 3, "note": "partial"},
            )
            first = store.get("tenant-a", "job_cp_1")
            assert first is not None
            self.assertEqual(first["stage"], "asr_started")
            self.assertEqual(first["stage_offset"], 3)
            self.assertEqual(first["payload"]["segments_done"], 3)

            store.upsert(
                tenant_id="tenant-a",
                job_id="job_cp_1",
                stage="diarization_done",
                stage_offset=0,
                payload={"complete": True},
            )
            second = store.get("tenant-a", "job_cp_1")
            assert second is not None
            self.assertEqual(second["stage"], "diarization_done")
            self.assertEqual(second["payload"]["complete"], True)

    def test_sqlite_job_checkpoint_store_delete_removes_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            store = SQLiteJobCheckpointStore(db_path)
            store.upsert(
                tenant_id="tenant-a",
                job_id="job_cp_2",
                stage="asr_started",
                stage_offset=1,
                payload={"segments_done": 1},
            )
            store.delete("tenant-a", "job_cp_2")
            self.assertIsNone(store.get("tenant-a", "job_cp_2"))

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
            self.assertEqual(len(audit.list_for_tenant(tenant_id="tenant-a")), 1)
            self.assertEqual(len(audit.list_for_tenant(tenant_id="tenant-b")), 0)

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

    def test_job_repo_mark_queued_persists_worker_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            repo.create(
                {
                    "job_id": "job_q1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.mp3",
                    "content_type": "audio/mpeg",
                    "size_bytes": 12,
                    "retention_months": 6,
                    "status": "upload_pending",
                }
            )

            repo.mark_queued(
                "tenant-a",
                "job_q1",
                object_key="tenant/tenant-a/job_q1/audio.mp3",
                checksum_sha256="a" * 64,
                upload_session_id="up_123",
                transcription_options={"beam_size": 4, "temperature": 0.2},
            )
            row = repo.get("tenant-a", "job_q1")
            self.assertEqual(row["status"], "queued")
            self.assertEqual(row["object_key"], "tenant/tenant-a/job_q1/audio.mp3")
            self.assertEqual(row["upload_session_id"], "up_123")
            self.assertEqual(row["checksum_sha256"], "a" * 64)
            self.assertEqual(json.loads(row["transcription_options_json"])["beam_size"], 4)

    def test_tenant_transcription_settings_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            store = SQLiteTenantTranscriptionSettingsStore(db_path)
            store.upsert(
                tenant_id="tenant-a",
                updated_by="admin-1",
                decoding_options={"beam_size": 4, "temperature": 0.3},
            )
            row = store.get("tenant-a")
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["tenant_id"], "tenant-a")
            self.assertEqual(row["updated_by"], "admin-1")
            self.assertEqual(row["decoding_options"]["beam_size"], 4)

    def test_transcript_repository_reads_worker_artifact_as_version_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            artifacts = SQLiteWorkerArtifactStore(db_path)
            artifacts.put_transcript(
                tenant_id="tenant-a",
                job_id="job_1",
                artifact={
                    "transcript": {"segments": [{"start": 0.0, "end": 1.0, "text": "Hallo"}]},
                    "diarization": {"segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]},
                },
            )

            repo = SQLiteTranscriptRepository(db_path)
            current = repo.get_current("tenant-a", "job_1")

            self.assertIsNotNone(current)
            assert current is not None
            self.assertEqual(current.version, 1)
            self.assertEqual(current.segments[0]["speaker"], "SPEAKER_00")
            self.assertEqual(current.segments[0]["text"], "Hallo")
            self.assertEqual(current.speaker_labels, {})

    def test_transcript_repository_save_new_version_enforces_optimistic_locking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            artifacts = SQLiteWorkerArtifactStore(db_path)
            artifacts.put_transcript(
                tenant_id="tenant-a",
                job_id="job_2",
                artifact={
                    "transcript": {"segments": [{"start": 0.0, "end": 1.0, "text": "Orig"}]},
                    "diarization": {"segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]},
                },
            )
            repo = SQLiteTranscriptRepository(db_path)

            v2 = repo.save_new_version(
                tenant_id="tenant-a",
                job_id="job_2",
                expected_base_version=1,
                segments=[{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Edited"}],
            )
            self.assertEqual(v2, 2)
            latest = repo.get_current("tenant-a", "job_2")
            assert latest is not None
            self.assertEqual(latest.version, 2)
            self.assertEqual(latest.segments[0]["text"], "Edited")
            self.assertEqual(latest.speaker_labels, {})

            with self.assertRaises(TranscriptConflictError):
                repo.save_new_version(
                    tenant_id="tenant-a",
                    job_id="job_2",
                    expected_base_version=1,
                    segments=[{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Stale"}],
                )

    def test_transcript_repository_persists_speaker_label_snapshots_per_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            artifacts = SQLiteWorkerArtifactStore(db_path)
            artifacts.put_transcript(
                tenant_id="tenant-a",
                job_id="job_alias_1",
                artifact={
                    "transcript": {"segments": [{"start": 0.0, "end": 1.0, "text": "Hallo"}]},
                    "diarization": {"segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0}]},
                },
            )
            repo = SQLiteTranscriptRepository(db_path)

            version_2 = repo.save_new_version(
                tenant_id="tenant-a",
                job_id="job_alias_1",
                expected_base_version=1,
                segments=[{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01", "text": "Hallo"}],
                speaker_labels={"SPEAKER_01": "Patrick"},
            )
            self.assertEqual(version_2, 2)

            current = repo.get_current("tenant-a", "job_alias_1")
            assert current is not None
            self.assertEqual(current.speaker_labels, {"SPEAKER_01": "Patrick"})

            version_1 = repo.get_version("tenant-a", "job_alias_1", 1)
            assert version_1 is not None
            self.assertEqual(version_1["speaker_labels"], {})
            version_2_payload = repo.get_version("tenant-a", "job_alias_1", 2)
            assert version_2_payload is not None
            self.assertEqual(version_2_payload["speaker_labels"], {"SPEAKER_01": "Patrick"})

    def test_delete_helpers_remove_worker_artifacts_and_transcript_versions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            artifacts = SQLiteWorkerArtifactStore(db_path)
            artifacts.put_transcript(
                tenant_id="tenant-a",
                job_id="job_3",
                artifact={
                    "transcript": {"segments": [{"start": 0.0, "end": 1.0, "text": "Orig"}]},
                    "diarization": {"segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]},
                },
            )
            repo = SQLiteTranscriptRepository(db_path)
            current = repo.get_current("tenant-a", "job_3")
            assert current is not None
            self.assertEqual(current.version, 1)

            artifacts.delete("tenant-a", "job_3")
            repo.delete("tenant-a", "job_3")

            self.assertIsNone(artifacts.get("tenant-a", "job_3"))
            self.assertIsNone(repo.get_current("tenant-a", "job_3"))

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
