import unittest

from evodox.jobs.complete_upload_service import (
    CompleteUploadInput,
    CompleteUploadValidationError,
    InMemoryCompleteUploadIdempotencyStore,
    InMemoryJobStore,
    InMemoryObjectStorage,
    InMemoryOutbox,
    InMemoryTenantTranscriptionSettingsStore,
    QueueSelectionPolicy,
    complete_upload,
)


class CompleteUploadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = InMemoryJobStore()
        self.storage = InMemoryObjectStorage()
        self.outbox = InMemoryOutbox()
        self.idempotency = InMemoryCompleteUploadIdempotencyStore()
        self.settings_store = InMemoryTenantTranscriptionSettingsStore()
        self.queue_policy = QueueSelectionPolicy()

        self.jobs.add_job(
            {
                "job_id": "job_1",
                "tenant_id": "tenant-a",
                "status": "uploaded",
                "content_type": "video/mp4",
                "size_bytes": 1_000_000,
            }
        )
        self.storage.put("tenant/tenant-a/job_1/hearing.mp4", checksum_sha256="a" * 64)

    def test_happy_path_queues_job_and_writes_outbox_event(self):
        self.settings_store.upsert(
            tenant_id="tenant-a",
            updated_by="admin-1",
            decoding_options={
                "temperature": 0.2,
                "beam_size": 4,
                "patience": 1.1,
                "length_penalty": 1.0,
                "compression_ratio_threshold": 2.2,
                "logprob_threshold": -1.0,
                "no_speech_threshold": 0.5,
                "suppress_tokens": "-1,12",
                "initial_prompt": "Juristische Fachbegriffe bevorzugen",
                "condition_on_previous_text": True,
            },
        )
        response = complete_upload(
            CompleteUploadInput(
                job_id="job_1",
                upload_session_id="up_1",
                object_key="tenant/tenant-a/job_1/hearing.mp4",
                checksum_sha256="a" * 64,
                idempotency_key="cpl-idempotent-1",
            ),
            tenant_id="tenant-a",
            actor_id="u-1",
            job_store=self.jobs,
            object_storage=self.storage,
            outbox=self.outbox,
            idempotency_store=self.idempotency,
            queue_policy=self.queue_policy,
            transcription_settings_store=self.settings_store,
        )

        self.assertEqual(response.status, "queued")
        self.assertEqual(response.queue, "gpu-standard")
        saved_job = self.jobs.get("tenant-a", "job_1")
        self.assertEqual(saved_job["status"], "queued")
        self.assertEqual(saved_job["object_key"], "tenant/tenant-a/job_1/hearing.mp4")
        self.assertEqual(saved_job["checksum_sha256"], "a" * 64)
        self.assertEqual(saved_job["upload_session_id"], "up_1")
        self.assertEqual(saved_job["transcription_options"]["beam_size"], 4)
        self.assertEqual(len(self.outbox.events), 1)
        self.assertEqual(self.outbox.events[0]["event_type"], "job.queued")
        self.assertEqual(self.outbox.events[0]["transcription_options"]["beam_size"], 4)

    def test_idempotent_repeat_returns_same_response_without_duplicate_event(self):
        request = CompleteUploadInput(
            job_id="job_1",
            upload_session_id="up_1",
            object_key="tenant/tenant-a/job_1/hearing.mp4",
            checksum_sha256="a" * 64,
            idempotency_key="cpl-idempotent-repeat",
        )

        first = complete_upload(
            request,
            tenant_id="tenant-a",
            actor_id="u-1",
            job_store=self.jobs,
            object_storage=self.storage,
            outbox=self.outbox,
            idempotency_store=self.idempotency,
            queue_policy=self.queue_policy,
        )
        second = complete_upload(
            request,
            tenant_id="tenant-a",
            actor_id="u-1",
            job_store=self.jobs,
            object_storage=self.storage,
            outbox=self.outbox,
            idempotency_store=self.idempotency,
            queue_policy=self.queue_policy,
        )

        self.assertEqual(first, second)
        self.assertEqual(len(self.outbox.events), 1)

    def test_idempotency_conflict_for_changed_payload(self):
        complete_upload(
            CompleteUploadInput(
                job_id="job_1",
                upload_session_id="up_1",
                object_key="tenant/tenant-a/job_1/hearing.mp4",
                checksum_sha256="a" * 64,
                idempotency_key="cpl-idempotent-conflict",
            ),
            tenant_id="tenant-a",
            actor_id="u-1",
            job_store=self.jobs,
            object_storage=self.storage,
            outbox=self.outbox,
            idempotency_store=self.idempotency,
            queue_policy=self.queue_policy,
        )

        with self.assertRaises(CompleteUploadValidationError) as exc_info:
            complete_upload(
                CompleteUploadInput(
                    job_id="job_1",
                    upload_session_id="up_1",
                    object_key="tenant/tenant-a/job_1/other.mp4",
                    checksum_sha256="a" * 64,
                    idempotency_key="cpl-idempotent-conflict",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                job_store=self.jobs,
                object_storage=self.storage,
                outbox=self.outbox,
                idempotency_store=self.idempotency,
                queue_policy=self.queue_policy,
            )

        self.assertEqual(exc_info.exception.error_code, "job.complete_upload.idempotency_conflict")

    def test_rejects_cross_tenant_job_access_without_leak(self):
        with self.assertRaises(CompleteUploadValidationError) as exc_info:
            complete_upload(
                CompleteUploadInput(
                    job_id="job_1",
                    upload_session_id="up_1",
                    object_key="tenant/tenant-b/job_1/hearing.mp4",
                    checksum_sha256="a" * 64,
                    idempotency_key="cpl-idempotent-2",
                ),
                tenant_id="tenant-b",
                actor_id="u-2",
                job_store=self.jobs,
                object_storage=self.storage,
                outbox=self.outbox,
                idempotency_store=self.idempotency,
                queue_policy=self.queue_policy,
            )

        self.assertEqual(exc_info.exception.error_code, "job.not_found")

    def test_rejects_when_storage_object_is_missing(self):
        with self.assertRaises(CompleteUploadValidationError) as exc_info:
            complete_upload(
                CompleteUploadInput(
                    job_id="job_1",
                    upload_session_id="up_1",
                    object_key="tenant/tenant-a/job_1/missing.mp4",
                    checksum_sha256="a" * 64,
                    idempotency_key="cpl-idempotent-3",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                job_store=self.jobs,
                object_storage=self.storage,
                outbox=self.outbox,
                idempotency_store=self.idempotency,
                queue_policy=self.queue_policy,
            )

        self.assertEqual(exc_info.exception.error_code, "job.complete_upload.object_missing")

    def test_rejects_invalid_checksum(self):
        with self.assertRaises(CompleteUploadValidationError) as exc_info:
            complete_upload(
                CompleteUploadInput(
                    job_id="job_1",
                    upload_session_id="up_1",
                    object_key="tenant/tenant-a/job_1/hearing.mp4",
                    checksum_sha256="invalid",
                    idempotency_key="cpl-idempotent-4",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                job_store=self.jobs,
                object_storage=self.storage,
                outbox=self.outbox,
                idempotency_store=self.idempotency,
                queue_policy=self.queue_policy,
            )

        self.assertEqual(exc_info.exception.error_code, "job.complete_upload.invalid_checksum")

    def test_audio_content_is_routed_to_gpu_standard(self):
        self.jobs.add_job(
            {
                "job_id": "job_audio_1",
                "tenant_id": "tenant-a",
                "status": "uploaded",
                "content_type": "audio/mpeg",
                "size_bytes": 2_000_000,
            }
        )
        self.storage.put("tenant/tenant-a/job_audio_1/audio.mp3", checksum_sha256="b" * 64)

        response = complete_upload(
            CompleteUploadInput(
                job_id="job_audio_1",
                upload_session_id="up_audio_1",
                object_key="tenant/tenant-a/job_audio_1/audio.mp3",
                checksum_sha256="b" * 64,
                idempotency_key="cpl-idempotent-audio-gpu",
            ),
            tenant_id="tenant-a",
            actor_id="u-1",
            job_store=self.jobs,
            object_storage=self.storage,
            outbox=self.outbox,
            idempotency_store=self.idempotency,
            queue_policy=self.queue_policy,
        )

        self.assertEqual(response.queue, "gpu-standard")

    def test_job_language_override_takes_priority_over_tenant_settings(self):
        self.jobs.add_job(
            {
                "job_id": "job_lang_1",
                "tenant_id": "tenant-a",
                "status": "uploaded",
                "content_type": "audio/mpeg",
                "size_bytes": 2_000_000,
                "transcription_options_json": {"language": "fr"},
            }
        )
        self.storage.put("tenant/tenant-a/job_lang_1/audio.mp3", checksum_sha256="c" * 64)
        self.settings_store.upsert(
            tenant_id="tenant-a",
            updated_by="admin-1",
            decoding_options={"language": "en", "beam_size": 6},
        )

        response = complete_upload(
            CompleteUploadInput(
                job_id="job_lang_1",
                upload_session_id="up_lang_1",
                object_key="tenant/tenant-a/job_lang_1/audio.mp3",
                checksum_sha256="c" * 64,
                idempotency_key="cpl-idempotent-lang-1",
            ),
            tenant_id="tenant-a",
            actor_id="u-1",
            job_store=self.jobs,
            object_storage=self.storage,
            outbox=self.outbox,
            idempotency_store=self.idempotency,
            queue_policy=self.queue_policy,
            transcription_settings_store=self.settings_store,
        )

        self.assertEqual(response.status, "queued")
        self.assertEqual(self.outbox.events[-1]["transcription_options"]["language"], "fr")
        self.assertEqual(self.outbox.events[-1]["transcription_options"]["beam_size"], 6)


if __name__ == "__main__":
    unittest.main()
