import unittest

from evodox.jobs.transcript_service import InMemoryTranscriptRepository, get_transcript
from evodox.jobs.transcript_correction_service import (
    CorrectionSessionApplyInput,
    CorrectionSessionCommitInput,
    CorrectionSessionCreateInput,
    InMemoryTranscriptCorrectionStore,
    TranscriptStatusUpdateInput,
    apply_correction_operations,
    commit_correction_session,
    create_correction_session,
    get_correction_session,
    redo_correction_session,
    undo_correction_session,
    update_transcript_status,
)


class TranscriptCorrectionServiceTests(unittest.TestCase):
    def test_create_session_uses_current_transcript_version(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_1",
            version=2,
            segments=[
                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hallo"},
                {"segment_id": "seg_2", "start": 1.0, "end": 2.0, "speaker": "S2", "text": "Welt"},
            ],
            speaker_labels={"S1": "Alice"},
        )
        corrections = InMemoryTranscriptCorrectionStore()

        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_1", autosave_enabled=True),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        self.assertEqual(session.base_version, 2)
        self.assertTrue(session.autosave_enabled)
        self.assertEqual(session.segments[0]["segment_id"], "seg_1")

    def test_apply_set_segments_rejects_timeline_gaps(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_2",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()
        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_2"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        with self.assertRaises(Exception):
            apply_correction_operations(
                CorrectionSessionApplyInput(
                    job_id="job_2",
                    session_id=session.session_id,
                    operations=[
                        {
                            "type": "set_segments",
                            "segments": [
                                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                                {"segment_id": "seg_2", "start": 1.5, "end": 2.0, "speaker": "S1", "text": "B"},
                            ],
                        }
                    ],
                ),
                tenant_id="tenant-a",
                actor_id="reviewer-1",
                correction_store=corrections,
                audit_log=[],
            )

    def test_create_session_compacts_seed_timeline_with_gaps(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_2b",
            version=1,
            segments=[
                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                {"segment_id": "seg_2", "start": 2.0, "end": 3.5, "speaker": "S2", "text": "B"},
            ],
        )
        corrections = InMemoryTranscriptCorrectionStore()

        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_2b"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        self.assertEqual(len(session.segments), 2)
        self.assertEqual(session.segments[0]["end"], session.segments[1]["start"])

    def test_partial_speaker_reassignment_splits_segment(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_3",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 10.0, "speaker": "S1", "text": "Hallo Welt"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()
        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_3"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        updated = apply_correction_operations(
            CorrectionSessionApplyInput(
                job_id="job_3",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "reassign_speaker",
                        "segment_id": "seg_1",
                        "speaker": "S2",
                        "start_char": 6,
                        "end_char": 10,
                    }
                ],
            ),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            correction_store=corrections,
            audit_log=[],
        )

        self.assertEqual(len(updated.segments), 2)
        self.assertEqual(updated.segments[1]["speaker"], "S2")
        self.assertEqual(updated.segments[0]["start"], 0.0)
        self.assertEqual(updated.segments[1]["end"], 10.0)

    def test_undo_and_redo_switch_history_index(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_4",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()
        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_4"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )
        apply_correction_operations(
            CorrectionSessionApplyInput(
                job_id="job_4",
                session_id=session.session_id,
                operations=[{"type": "replace_literal", "query": "A", "replace": "B"}],
            ),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            correction_store=corrections,
            audit_log=[],
        )

        undone = undo_correction_session(
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            job_id="job_4",
            session_id=session.session_id,
            correction_store=corrections,
            audit_log=[],
        )
        redone = redo_correction_session(
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            job_id="job_4",
            session_id=session.session_id,
            correction_store=corrections,
            audit_log=[],
        )

        self.assertEqual(undone.segments[0]["text"], "A")
        self.assertEqual(redone.segments[0]["text"], "B")

    def test_commit_persists_new_transcript_version(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_5",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()
        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_5"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )
        apply_correction_operations(
            CorrectionSessionApplyInput(
                job_id="job_5",
                session_id=session.session_id,
                operations=[{"type": "replace_literal", "query": "A", "replace": "B"}],
            ),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            correction_store=corrections,
            audit_log=[],
        )

        result = commit_correction_session(
            CorrectionSessionCommitInput(
                job_id="job_5",
                session_id=session.session_id,
                base_version=1,
                edit_reason="Korrektur",
            ),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )
        current = get_transcript(tenant_id="tenant-a", job_id="job_5", transcript_repo=transcripts)

        self.assertEqual(result.version, 2)
        self.assertEqual(current.segments[0]["text"], "B")

    def test_status_update_sets_final(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_6",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()

        status = update_transcript_status(
            TranscriptStatusUpdateInput(job_id="job_6", review_status="reviewed", is_final=True),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        self.assertEqual(status.review_status, "reviewed")
        self.assertTrue(status.is_final)
        self.assertEqual(status.final_set_by, "reviewer-1")

    def test_get_session_forbidden_for_other_actor(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_7",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()
        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_7"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        with self.assertRaises(Exception):
            get_correction_session(
                tenant_id="tenant-a",
                actor_id="reviewer-2",
                job_id="job_7",
                session_id=session.session_id,
                correction_store=corrections,
            )

    def test_status_update_rejects_unknown_job(self):
        transcripts = InMemoryTranscriptRepository()
        corrections = InMemoryTranscriptCorrectionStore()

        with self.assertRaises(Exception):
            update_transcript_status(
                TranscriptStatusUpdateInput(job_id="missing-job", review_status="reviewed", is_final=True),
                tenant_id="tenant-a",
                actor_id="reviewer-1",
                transcript_repo=transcripts,
                correction_store=corrections,
                audit_log=[],
            )


if __name__ == "__main__":
    unittest.main()
