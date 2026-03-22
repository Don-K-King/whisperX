import unittest

from evodox.auth.context import AuthContext
from evodox.jobs.create_service import CreateJobResponse, UploadSession
from evodox.web.fastapi_adapter import map_create_job_response


class HttpAdapterCoreTests(unittest.TestCase):
    def test_maps_domain_response_to_api_contract_shape(self):
        response = CreateJobResponse(
            job_id="job_1",
            tenant_id="tenant-a",
            status="upload_pending",
            upload=UploadSession(
                session_id="up_1",
                object_key="tenant/tenant-a/job_1/file.mp4",
                presigned_url="https://minio.local/upload/tenant/tenant-a/job_1/file.mp4",
                expires_at="2030-01-01T00:00:00+00:00",
            ),
        )

        payload = map_create_job_response(response)

        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["tenant_id"], "tenant-a")
        self.assertEqual(payload["status"], "upload_pending")
        self.assertEqual(payload["upload"]["session_id"], "up_1")


if __name__ == "__main__":
    unittest.main()
