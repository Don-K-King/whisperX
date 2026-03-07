import unittest

from evodox.jobs.complete_upload_service import CompleteUploadResponse
from evodox.web.fastapi_adapter import map_complete_upload_response


class CompleteUploadHttpAdapterTests(unittest.TestCase):
    def test_map_complete_upload_response(self):
        payload = map_complete_upload_response(
            CompleteUploadResponse(job_id="job_1", status="queued", queue="gpu-standard")
        )
        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["queue"], "gpu-standard")


if __name__ == "__main__":
    unittest.main()
