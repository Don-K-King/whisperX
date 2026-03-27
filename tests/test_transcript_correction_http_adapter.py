import unittest

from evodox.web.fastapi_adapter import (
    map_correction_session_response,
    map_transcript_status_response,
)


class TranscriptCorrectionHttpAdapterTests(unittest.TestCase):
    def test_maps_correction_session_response(self):
        class Session:
            session_id = "cs_1"
            job_id = "job_1"
            base_version = 2
            working_version = 4
            autosave_enabled = True
            history_index = 2
            segments = [{"segment_id": "seg_1", "text": "Hallo"}]
            speaker_labels = {"S1": "Alice"}
            operation_log = [{"type": "replace_literal"}]
            review_status = "reviewed"
            is_final = True
            changed_segments = [{"segment_id": "seg_1", "text": "Hallo"}]
            removed_segment_ids = ["seg_99"]

        payload = map_correction_session_response(Session())
        self.assertEqual(payload["session_id"], "cs_1")
        self.assertEqual(payload["working_version"], 4)
        self.assertEqual(payload["review_status"], "reviewed")
        self.assertEqual(payload["return_mode"], "full")

    def test_maps_correction_session_response_changed_segments_mode(self):
        class Session:
            session_id = "cs_1"
            job_id = "job_1"
            base_version = 2
            working_version = 4
            autosave_enabled = True
            history_index = 2
            segments = [{"segment_id": "seg_1", "text": "Hallo"}]
            speaker_labels = {"S1": "Alice"}
            operation_log = [{"type": "replace_literal"}]
            review_status = "reviewed"
            is_final = True
            changed_segments = [{"segment_id": "seg_1", "text": "Neu"}]
            removed_segment_ids = ["seg_2"]

        payload = map_correction_session_response(Session(), return_mode="changed_segments")
        self.assertEqual(payload["return_mode"], "changed_segments")
        self.assertEqual(payload["segments"], [{"segment_id": "seg_1", "text": "Neu"}])
        self.assertEqual(payload["removed_segment_ids"], ["seg_2"])

    def test_maps_correction_session_response_ack_mode(self):
        class Session:
            session_id = "cs_1"
            job_id = "job_1"
            base_version = 2
            working_version = 4
            autosave_enabled = True
            history_index = 2
            segments = [{"segment_id": "seg_1", "text": "Hallo"}]
            speaker_labels = {"S1": "Alice"}
            operation_log = [{"type": "replace_literal"}]
            review_status = "reviewed"
            is_final = True
            changed_segments = [{"segment_id": "seg_1", "text": "Neu"}]
            removed_segment_ids = ["seg_2", "seg_3"]

        payload = map_correction_session_response(Session(), return_mode="ack")
        self.assertEqual(payload["return_mode"], "ack")
        self.assertEqual(payload["changed_segments_count"], 1)
        self.assertEqual(payload["removed_segments_count"], 2)

    def test_maps_transcript_status_response(self):
        class Status:
            job_id = "job_1"
            review_status = "reviewed"
            is_final = True
            final_set_by = "u-1"
            final_set_at = "2026-03-24T18:00:00+00:00"
            updated_at = "2026-03-24T18:00:00+00:00"

        payload = map_transcript_status_response(Status())
        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["is_final"], True)
        self.assertEqual(payload["final_set_by"], "u-1")


if __name__ == "__main__":
    unittest.main()
