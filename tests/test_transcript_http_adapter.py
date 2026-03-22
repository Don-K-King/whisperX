import unittest

from evodox.jobs.transcript_service import TranscriptResponse, UpdateTranscriptResponse
from evodox.web.fastapi_adapter import map_transcript_response, map_transcript_update_response


class TranscriptHttpAdapterTests(unittest.TestCase):
    def test_maps_get_transcript_response(self):
        payload = map_transcript_response(
            TranscriptResponse(
                job_id="job_1",
                version=3,
                segments=[{"start": 0.0, "end": 1.0, "speaker": "S1", "text": "Hi"}],
            )
        )
        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["version"], 3)

    def test_maps_put_transcript_response(self):
        payload = map_transcript_update_response(
            UpdateTranscriptResponse(job_id="job_1", version=4, saved_at="2026-03-08T12:00:00+00:00")
        )
        self.assertEqual(payload["version"], 4)
        self.assertIn("saved_at", payload)


if __name__ == "__main__":
    unittest.main()
