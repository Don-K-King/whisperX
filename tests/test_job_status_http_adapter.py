import unittest

from evodox.jobs.get_job_status_service import JobStatusResponse
from evodox.web.fastapi_adapter import map_job_status_response


class JobStatusHttpAdapterTests(unittest.TestCase):
    def test_maps_job_status_payload(self):
        payload = map_job_status_response(
            JobStatusResponse(
                job_id="job_1",
                status="processing",
                progress=42,
                retention_until="2027-01-01T00:00:00+00:00",
            )
        )

        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["status"], "processing")
        self.assertEqual(payload["progress"], 42)
        self.assertIn("retention_until", payload)


if __name__ == "__main__":
    unittest.main()
