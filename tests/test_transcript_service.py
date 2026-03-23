import unittest

from evodox.jobs.transcript_service import (
    InMemoryTranscriptRepository,
    TranscriptConflictError,
    TranscriptValidationError,
    UpdateTranscriptInput,
    UpdateTranscriptSpeakerLabelsInput,
    get_transcript,
    update_transcript,
    update_transcript_speaker_labels,
)


class TranscriptServiceTests(unittest.TestCase):
    def test_get_transcript_returns_current_version(self):
        repo = InMemoryTranscriptRepository()
        repo.seed(
            tenant_id="tenant-a",
            job_id="job_1",
            version=2,
            segments=[{"start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hallo"}],
            speaker_labels={"S1": "Patrick"},
        )

        response = get_transcript(tenant_id="tenant-a", job_id="job_1", transcript_repo=repo)

        self.assertEqual(response.version, 2)
        self.assertEqual(response.segments[0]["text"], "Hallo")
        self.assertEqual(response.speaker_labels["S1"], "Patrick")

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

    def test_update_transcript_speaker_labels_creates_new_version_and_keeps_segments(self):
        repo = InMemoryTranscriptRepository()
        repo.seed(
            tenant_id="tenant-a",
            job_id="job_4",
            version=1,
            segments=[{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01", "text": "Hallo"}],
            speaker_labels={},
        )
        audit_log: list[dict[str, str]] = []

        result = update_transcript_speaker_labels(
            UpdateTranscriptSpeakerLabelsInput(
                job_id="job_4",
                base_version=1,
                speaker_labels={"SPEAKER_01": "Patrick", "SPEAKER_02": ""},
                edit_reason="Speaker labels",
            ),
            tenant_id="tenant-a",
            actor_id="u-1",
            transcript_repo=repo,
            audit_log=audit_log,
        )

        self.assertEqual(result.version, 2)
        current = get_transcript(tenant_id="tenant-a", job_id="job_4", transcript_repo=repo)
        self.assertEqual(current.segments[0]["text"], "Hallo")
        self.assertEqual(current.speaker_labels, {"SPEAKER_01": "Patrick"})
        self.assertEqual(audit_log[0]["action"], "transcript.speaker_labels.updated")

    def test_update_transcript_speaker_labels_enforces_optimistic_locking(self):
        repo = InMemoryTranscriptRepository()
        repo.seed(
            tenant_id="tenant-a",
            job_id="job_5",
            version=2,
            segments=[{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01", "text": "Hallo"}],
        )

        with self.assertRaises(TranscriptConflictError):
            update_transcript_speaker_labels(
                UpdateTranscriptSpeakerLabelsInput(
                    job_id="job_5",
                    base_version=1,
                    speaker_labels={"SPEAKER_01": "Patrick"},
                    edit_reason="Speaker labels",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                transcript_repo=repo,
                audit_log=[],
            )

    def test_update_transcript_speaker_labels_rejects_control_characters(self):
        repo = InMemoryTranscriptRepository()
        repo.seed(
            tenant_id="tenant-a",
            job_id="job_6",
            version=1,
            segments=[{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01", "text": "Hallo"}],
        )

        with self.assertRaises(TranscriptValidationError):
            update_transcript_speaker_labels(
                UpdateTranscriptSpeakerLabelsInput(
                    job_id="job_6",
                    base_version=1,
                    speaker_labels={"SPEAKER_01": "Patr\x00ick"},
                    edit_reason="Speaker labels",
                ),
                tenant_id="tenant-a",
                actor_id="u-1",
                transcript_repo=repo,
                audit_log=[],
            )


if __name__ == "__main__":
    unittest.main()
