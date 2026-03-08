import unittest

from evodox.jobs.transcript_service import (
    InMemoryTranscriptRepository,
    TranscriptConflictError,
    TranscriptValidationError,
    UpdateTranscriptInput,
    get_transcript,
    update_transcript,
)


class TranscriptServiceTests(unittest.TestCase):
    def test_get_transcript_returns_current_version(self):
        repo = InMemoryTranscriptRepository()
        repo.seed(
            tenant_id="tenant-a",
            job_id="job_1",
            version=2,
            segments=[{"start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hallo"}],
        )

        response = get_transcript(tenant_id="tenant-a", job_id="job_1", transcript_repo=repo)

        self.assertEqual(response.version, 2)
        self.assertEqual(response.segments[0]["text"], "Hallo")

    def test_update_transcript_enforces_optimistic_locking(self):
        repo = InMemoryTranscriptRepository()
        repo.seed(
            tenant_id="tenant-a",
            job_id="job_2",
            version=3,
            segments=[{"start": 0.0, "end": 1.0, "speaker": "S1", "text": "Original"}],
        )

        with self.assertRaises(TranscriptConflictError):
            update_transcript(
                UpdateTranscriptInput(
                    job_id="job_2",
                    base_version=2,
                    segments=[{"segment_id": "seg-1", "speaker": "S1", "text": "Neu"}],
                    edit_reason="Korrektur",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                transcript_repo=repo,
                audit_log=[],
            )

    def test_update_transcript_rejects_cross_tenant_segment_text_abuse(self):
        repo = InMemoryTranscriptRepository()
        repo.seed(
            tenant_id="tenant-a",
            job_id="job_3",
            version=1,
            segments=[{"start": 0.0, "end": 1.0, "speaker": "S1", "text": "Original"}],
        )

        with self.assertRaises(TranscriptValidationError):
            update_transcript(
                UpdateTranscriptInput(
                    job_id="job_3",
                    base_version=1,
                    segments=[{"segment_id": "seg-1", "speaker": "S1", "text": "\x00<script>alert(1)</script>"}],
                    edit_reason="clean-up",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                transcript_repo=repo,
                audit_log=[],
            )


if __name__ == "__main__":
    unittest.main()
