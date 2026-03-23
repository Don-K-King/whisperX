import unittest

from evodox.jobs.export_service import (
    ExportRequestInput,
    ExportValidationError,
    InMemoryExportArtifactStore,
    InMemoryTranscriptReadRepository,
    queue_export,
)


class ExportServiceTests(unittest.TestCase):
    def test_queues_export_and_renders_srt(self):
        transcripts = InMemoryTranscriptReadRepository(
            {
                ("tenant-a", "job_1", 2): {
                    "segments": [
                        {"start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hi"},
                    ],
                    "speaker_labels": {"S1": "Patrick"},
                }
            }
        )
        exports = InMemoryExportArtifactStore()

        result = queue_export(
            ExportRequestInput(job_id="job_1", transcript_version=2, format="srt", idempotency_key="idem-1234"),
            tenant_id="tenant-a",
            actor_id="u-1",
            transcript_repo=transcripts,
            export_store=exports,
            audit_log=[],
        )

        self.assertEqual(result.status, "queued")
        artifact = exports.get("tenant-a", result.export_id)
        self.assertIn("00:00:00,000", artifact["content"])
        self.assertNotIn("Patrick", artifact["content"])

    def test_json_export_applies_speaker_labels(self):
        transcripts = InMemoryTranscriptReadRepository(
            {
                ("tenant-a", "job_1", 2): {
                    "segments": [
                        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01", "text": "Hi"},
                    ],
                    "speaker_labels": {"SPEAKER_01": "Patrick"},
                }
            }
        )
        exports = InMemoryExportArtifactStore()

        result = queue_export(
            ExportRequestInput(job_id="job_1", transcript_version=2, format="json", idempotency_key="idem-1234"),
            tenant_id="tenant-a",
            actor_id="u-1",
            transcript_repo=transcripts,
            export_store=exports,
            audit_log=[],
        )

        artifact = exports.get("tenant-a", result.export_id)
        assert artifact is not None
        self.assertIn('"speaker": "Patrick"', artifact["content"])

    def test_rejects_unsupported_format(self):
        with self.assertRaises(ExportValidationError):
            queue_export(
                ExportRequestInput(job_id="job_1", transcript_version=2, format="exe", idempotency_key="idem-1234"),
                tenant_id="tenant-a",
                actor_id="u-1",
                transcript_repo=InMemoryTranscriptReadRepository({}),
                export_store=InMemoryExportArtifactStore(),
                audit_log=[],
            )


if __name__ == "__main__":
    unittest.main()
