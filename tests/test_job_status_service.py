import unittest

from evodox.jobs.get_job_status_service import (
    InMemoryJobStatusStore,
    JobStatusNotFoundError,
    get_job_status,
)


class JobStatusServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryJobStatusStore()
        self.store.add(
            {
                "job_id": "job_1",
                "tenant_id": "tenant-a",
                "status": "processing",
                "progress": 42,
                "retention_months": 12,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )

    def test_returns_status_for_same_tenant(self):
        result = get_job_status(job_id="job_1", tenant_id="tenant-a", job_store=self.store)

        self.assertEqual(result.job_id, "job_1")
        self.assertEqual(result.status, "processing")
        self.assertEqual(result.progress, 42)
        self.assertTrue(result.retention_until)

    def test_cross_tenant_access_returns_not_found(self):
        with self.assertRaises(JobStatusNotFoundError) as exc_info:
            get_job_status(job_id="job_1", tenant_id="tenant-b", job_store=self.store)

        self.assertEqual(exc_info.exception.error_code, "job.not_found")

    def test_defaults_progress_by_status_when_missing(self):
        self.store.add(
            {
                "job_id": "job_2",
                "tenant_id": "tenant-a",
                "status": "queued",
                "retention_months": 6,
                "created_at": "2026-02-01T00:00:00+00:00",
            }
        )

        result = get_job_status(job_id="job_2", tenant_id="tenant-a", job_store=self.store)
        self.assertEqual(result.progress, 5)


if __name__ == "__main__":
    unittest.main()
