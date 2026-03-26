import unittest

from evodox.jobs.transcript_service import (
    InMemoryTranscriptRepository,
    TranscriptValidationError,
    get_transcript,
)
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
    class _LegacyResumeCorrectionStore(InMemoryTranscriptCorrectionStore):
        def __init__(self, existing_session: dict):
            super().__init__()
            self._existing_session = dict(existing_session)

        def create_session(self, *, tenant_id: str, payload: dict):
            del tenant_id, payload
            return dict(self._existing_session)

        def get_session(self, *, tenant_id: str, session_id: str):
            del tenant_id
            if str(self._existing_session.get("session_id")) != str(session_id):
                return None
            return dict(self._existing_session)

        def update_session(self, *, tenant_id: str, session_id: str, payload: dict):
            del tenant_id
            if str(self._existing_session.get("session_id")) != str(session_id):
                raise KeyError("session not found")
            self._existing_session = dict(payload)
            return dict(self._existing_session)

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

    def test_create_session_reseeds_from_transcript_when_legacy_resume_detected(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_legacy",
            version=3,
            segments=[
                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                {"segment_id": "seg_2", "start": 4.5, "end": 6.0, "speaker": "S2", "text": "B"},
            ],
            speaker_labels={"S1": "Alice", "S2": "Bob"},
        )
        legacy = self._LegacyResumeCorrectionStore(
            {
                "session_id": "cs_legacy",
                "job_id": "job_legacy",
                "actor_id": "old-reviewer",
                "base_version": 2,
                "autosave_enabled": True,
                "speaker_labels": {"S1": "Legacy"},
                "review_status": "in_review",
                "is_final": False,
                "history_index": 1,
                "history": [
                    {
                        "segments": [
                            {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                            {"segment_id": "seg_2", "start": 1.0, "end": 2.5, "speaker": "S2", "text": "B"},
                        ],
                        "summary": None,
                    },
                    {
                        "segments": [
                            {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A!"},
                            {"segment_id": "seg_2", "start": 1.0, "end": 2.5, "speaker": "S2", "text": "B!"},
                        ],
                        "summary": {"operations": [{"type": "replace_literal"}]},
                    },
                ],
                "updated_at": "2026-03-20T00:00:00+00:00",
                "created_at": "2026-03-20T00:00:00+00:00",
            }
        )

        session = create_correction_session(
            CorrectionSessionCreateInput(
                job_id="job_legacy",
                base_version=3,
                autosave_enabled=False,
                force_reseed_from_transcript=True,
            ),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=legacy,
            audit_log=[],
        )

        self.assertEqual(session.session_id, "cs_legacy")
        self.assertEqual(session.base_version, 3)
        self.assertEqual(session.history_index, 0)
        self.assertFalse(session.autosave_enabled)
        self.assertEqual(session.speaker_labels, {"S1": "Alice", "S2": "Bob"})
        self.assertEqual(session.segments[0]["start"], 0.0)
        self.assertEqual(session.segments[0]["end"], 1.0)
        self.assertEqual(session.segments[1]["start"], 4.5)
        self.assertEqual(session.segments[1]["end"], 6.0)

    def test_create_session_preserves_absolute_timestamps_after_reseed(self):
        transcripts = InMemoryTranscriptRepository()
        expected_segments = [
            {"segment_id": "seg_1", "start": 0.25, "end": 2.75, "speaker": "S1", "text": "Hallo"},
            {"segment_id": "seg_2", "start": 7.0, "end": 9.125, "speaker": "S2", "text": "Welt"},
            {"segment_id": "seg_3", "start": 19.333, "end": 21.5, "speaker": "S1", "text": "Ende"},
        ]
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_legacy_precise",
            version=4,
            segments=expected_segments,
        )
        legacy = self._LegacyResumeCorrectionStore(
            {
                "session_id": "cs_legacy_precise",
                "job_id": "job_legacy_precise",
                "actor_id": "old-reviewer",
                "base_version": 1,
                "autosave_enabled": True,
                "speaker_labels": {},
                "review_status": "in_review",
                "is_final": False,
                "history_index": 0,
                "history": [
                    {
                        "segments": [
                            {"segment_id": "seg_1", "start": 0.0, "end": 2.5, "speaker": "S1", "text": "Hallo"},
                            {"segment_id": "seg_2", "start": 2.5, "end": 4.625, "speaker": "S2", "text": "Welt"},
                            {"segment_id": "seg_3", "start": 4.625, "end": 6.792, "speaker": "S1", "text": "Ende"},
                        ],
                        "summary": None,
                    }
                ],
                "updated_at": "2026-03-20T00:00:00+00:00",
                "created_at": "2026-03-20T00:00:00+00:00",
            }
        )

        session = create_correction_session(
            CorrectionSessionCreateInput(
                job_id="job_legacy_precise",
                base_version=4,
                force_reseed_from_transcript=True,
            ),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=legacy,
            audit_log=[],
        )

        observed = [(item["start"], item["end"]) for item in session.segments]
        expected = [(item["start"], item["end"]) for item in expected_segments]
        self.assertEqual(observed, expected)

    def test_set_segments_allows_timeline_gaps(self):
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

        updated = apply_correction_operations(
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
        self.assertEqual(updated.segments[1]["start"], 1.5)
        self.assertEqual(updated.segments[1]["end"], 2.0)

    def test_create_session_preserves_seed_timeline_with_gaps(self):
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
        self.assertEqual(session.segments[0]["start"], 0.0)
        self.assertEqual(session.segments[0]["end"], 1.0)
        self.assertEqual(session.segments[1]["start"], 2.0)
        self.assertEqual(session.segments[1]["end"], 3.5)

    def test_create_session_snaps_small_seed_overlap(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_overlap_small",
            version=1,
            segments=[
                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                {"segment_id": "seg_2", "start": 0.98, "end": 2.0, "speaker": "S2", "text": "B"},
            ],
        )
        corrections = InMemoryTranscriptCorrectionStore()

        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_overlap_small"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        self.assertEqual(session.segments[0]["end"], 1.0)
        self.assertEqual(session.segments[1]["start"], 1.0)
        self.assertEqual(session.segments[1]["end"], 2.0)

    def test_create_session_rejects_large_seed_overlap(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_overlap_large",
            version=1,
            segments=[
                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                {"segment_id": "seg_2", "start": 0.7, "end": 2.0, "speaker": "S2", "text": "B"},
            ],
        )
        corrections = InMemoryTranscriptCorrectionStore()

        with self.assertRaises(TranscriptValidationError) as ctx:
            create_correction_session(
                CorrectionSessionCreateInput(job_id="job_overlap_large"),
                tenant_id="tenant-a",
                actor_id="reviewer-1",
                transcript_repo=transcripts,
                correction_store=corrections,
                audit_log=[],
            )

        self.assertEqual(ctx.exception.error_code, "transcript.timeline_overlap")

    def test_set_segments_rejects_overlap_still(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_2c",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()
        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_2c"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        with self.assertRaises(TranscriptValidationError) as ctx:
            apply_correction_operations(
                CorrectionSessionApplyInput(
                    job_id="job_2c",
                    session_id=session.session_id,
                    operations=[
                        {
                            "type": "set_segments",
                            "segments": [
                                {"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"},
                                {"segment_id": "seg_2", "start": 0.8, "end": 1.5, "speaker": "S2", "text": "B"},
                            ],
                        }
                    ],
                ),
                tenant_id="tenant-a",
                actor_id="reviewer-1",
                correction_store=corrections,
                audit_log=[],
            )
        self.assertEqual(ctx.exception.error_code, "transcript.timeline_overlap")

    def test_set_segments_rejects_nan_inf_negative(self):
        transcripts = InMemoryTranscriptRepository()
        transcripts.seed(
            tenant_id="tenant-a",
            job_id="job_2d",
            version=1,
            segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "speaker": "S1", "text": "A"}],
        )
        corrections = InMemoryTranscriptCorrectionStore()
        session = create_correction_session(
            CorrectionSessionCreateInput(job_id="job_2d"),
            tenant_id="tenant-a",
            actor_id="reviewer-1",
            transcript_repo=transcripts,
            correction_store=corrections,
            audit_log=[],
        )

        invalid_timeline_samples = [
            {"start": float("nan"), "end": 1.0},
            {"start": 0.0, "end": float("inf")},
            {"start": -1.0, "end": 0.0},
        ]
        for idx, sample in enumerate(invalid_timeline_samples, start=1):
            with self.subTest(sample=sample):
                with self.assertRaises(TranscriptValidationError) as ctx:
                    apply_correction_operations(
                        CorrectionSessionApplyInput(
                            job_id="job_2d",
                            session_id=session.session_id,
                            operations=[
                                {
                                    "type": "set_segments",
                                    "segments": [
                                        {
                                            "segment_id": f"seg_invalid_{idx}",
                                            "start": sample["start"],
                                            "end": sample["end"],
                                            "speaker": "S1",
                                            "text": "A",
                                        }
                                    ],
                                }
                            ],
                        ),
                        tenant_id="tenant-a",
                        actor_id="reviewer-1",
                        correction_store=corrections,
                        audit_log=[],
                    )
                self.assertEqual(ctx.exception.error_code, "transcript.invalid_timeline")

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
