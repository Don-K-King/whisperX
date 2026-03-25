import unittest

from evodox.jobs.transcription_settings_service import (
    InMemoryTenantTranscriptionSettingsStore,
    TranscriptionSettingsValidationError,
    get_transcription_settings,
    update_transcription_settings,
)


class TranscriptionSettingsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryTenantTranscriptionSettingsStore()
        self.audit_log: list[dict] = []

    def test_get_returns_defaults_when_tenant_has_no_settings(self) -> None:
        result = get_transcription_settings(
            tenant_id="tenant-a",
            actor_id="admin-1",
            settings_store=self.store,
            audit_log=self.audit_log,
        )

        self.assertEqual(result["tenant_id"], "tenant-a")
        self.assertEqual(result["decoding_options"]["beam_size"], 5)
        self.assertEqual(result["decoding_options"]["temperature"], 0.0)
        self.assertEqual(result["decoding_options"]["condition_on_previous_text"], False)
        self.assertEqual(result["decoding_options"]["chunk_size"], 30)
        self.assertEqual(result["decoding_options"]["vad_onset"], 0.5)
        self.assertEqual(result["decoding_options"]["vad_offset"], 0.363)
        self.assertEqual(result["decoding_options"]["language"], "auto")
        self.assertEqual(len(self.audit_log), 1)
        self.assertEqual(self.audit_log[0]["action"], "transcription_settings.read")
        self.assertNotIn("initial_prompt", self.audit_log[0])

    def test_update_roundtrip_persists_options(self) -> None:
        update = update_transcription_settings(
            tenant_id="tenant-a",
            actor_id="admin-1",
            payload={
                "temperature": 0.4,
                "beam_size": 4,
                "patience": 1.1,
                "length_penalty": 1.0,
                "compression_ratio_threshold": 2.3,
                "logprob_threshold": -1.1,
                "no_speech_threshold": 0.5,
                "suppress_tokens": "-1,12",
                "initial_prompt": "Fachsprache beachten",
                "condition_on_previous_text": True,
                "chunk_size": 24,
                "vad_onset": 0.4,
                "vad_offset": 0.3,
                "language": "de",
            },
            settings_store=self.store,
            audit_log=self.audit_log,
        )

        self.assertEqual(update["decoding_options"]["temperature"], 0.4)
        self.assertEqual(update["decoding_options"]["chunk_size"], 24)
        self.assertEqual(update["decoding_options"]["language"], "de")
        fetched = get_transcription_settings(
            tenant_id="tenant-a",
            actor_id="admin-1",
            settings_store=self.store,
            audit_log=self.audit_log,
        )
        self.assertEqual(fetched["decoding_options"]["temperature"], 0.4)
        self.assertEqual(fetched["decoding_options"]["suppress_tokens"], "-1,12")
        self.assertEqual(fetched["decoding_options"]["vad_onset"], 0.4)
        self.assertEqual(fetched["decoding_options"]["vad_offset"], 0.3)
        update_events = [e for e in self.audit_log if e.get("action") == "transcription_settings.updated"]
        self.assertEqual(len(update_events), 1)
        self.assertNotIn("initial_prompt", update_events[0])
        self.assertIn("initial_prompt_sha256", update_events[0])

    def test_update_rejects_unknown_field(self) -> None:
        with self.assertRaises(TranscriptionSettingsValidationError) as exc:
            update_transcription_settings(
                tenant_id="tenant-a",
                actor_id="admin-1",
                payload={"beam_size": 5, "unknown_option": True},
                settings_store=self.store,
                audit_log=self.audit_log,
            )
        self.assertEqual(exc.exception.error_code, "transcription_settings.invalid_payload")

    def test_update_rejects_out_of_range_values(self) -> None:
        with self.assertRaises(TranscriptionSettingsValidationError) as exc:
            update_transcription_settings(
                tenant_id="tenant-a",
                actor_id="admin-1",
                payload={"temperature": 2.0},
                settings_store=self.store,
                audit_log=self.audit_log,
            )
        self.assertEqual(exc.exception.error_code, "transcription_settings.invalid_payload")

    def test_update_rejects_invalid_suppress_tokens_csv(self) -> None:
        with self.assertRaises(TranscriptionSettingsValidationError) as exc:
            update_transcription_settings(
                tenant_id="tenant-a",
                actor_id="admin-1",
                payload={"suppress_tokens": "-1,abc"},
                settings_store=self.store,
                audit_log=self.audit_log,
            )
        self.assertEqual(exc.exception.error_code, "transcription_settings.invalid_payload")

    def test_update_rejects_out_of_range_chunk_size(self) -> None:
        with self.assertRaises(TranscriptionSettingsValidationError) as exc:
            update_transcription_settings(
                tenant_id="tenant-a",
                actor_id="admin-1",
                payload={"chunk_size": 2},
                settings_store=self.store,
                audit_log=self.audit_log,
            )
        self.assertEqual(exc.exception.error_code, "transcription_settings.invalid_payload")

    def test_update_rejects_unsupported_language(self) -> None:
        with self.assertRaises(TranscriptionSettingsValidationError) as exc:
            update_transcription_settings(
                tenant_id="tenant-a",
                actor_id="admin-1",
                payload={"language": "xx"},
                settings_store=self.store,
                audit_log=self.audit_log,
            )
        self.assertEqual(exc.exception.error_code, "transcription_settings.invalid_payload")


if __name__ == "__main__":
    unittest.main()
