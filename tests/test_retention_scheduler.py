from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from evodox.jobs.retention_scheduler import (
    InMemoryRetentionRetryStore,
    InMemorySchedulerLeaseStore,
    RetentionFailureRecord,
    RetentionScheduler,
)
from evodox.jobs.retention_service import RetentionRunSummary


class _JobStub:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, *, batch_size: int) -> RetentionRunSummary:
        self.calls += 1
        return RetentionRunSummary(processed=1, deleted=1, skipped=0, failed=0)


class _RecoveryExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def retry(self, record: RetentionFailureRecord) -> bool:
        self.calls.append(record.failure_class)
        return record.failure_class == "db_mark_failed"


class RetentionSchedulerTests(unittest.TestCase):
    def test_scheduler_runs_only_when_interval_is_due(self) -> None:
        now = datetime(2026, 3, 8, tzinfo=timezone.utc)
        lease = InMemorySchedulerLeaseStore()
        retry_store = InMemoryRetentionRetryStore()
        job = _JobStub()
        scheduler = RetentionScheduler(
            retention_job=job,
            retry_store=retry_store,
            recovery_executor=_RecoveryExecutor(),
            lease_store=lease,
            interval=timedelta(minutes=30),
            now_factory=lambda: now,
        )

        first = scheduler.tick(batch_size=10)
        second = scheduler.tick(batch_size=10)

        self.assertTrue(first.executed)
        self.assertFalse(second.executed)
        self.assertEqual(job.calls, 1)

    def test_scheduler_retries_partial_failures_idempotently_per_failure_class(self) -> None:
        now = datetime(2026, 3, 8, tzinfo=timezone.utc)
        lease = InMemorySchedulerLeaseStore()
        retry_store = InMemoryRetentionRetryStore(
            [
                RetentionFailureRecord(
                    failure_id="f-1",
                    tenant_id="tenant-a",
                    job_id="job-1",
                    failure_class="db_mark_failed",
                    first_failed_at=now - timedelta(minutes=10),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=0,
                ),
                RetentionFailureRecord(
                    failure_id="f-2",
                    tenant_id="tenant-a",
                    job_id="job-1",
                    failure_class="storage_delete_failed",
                    first_failed_at=now - timedelta(minutes=10),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=0,
                ),
            ]
        )
        job = _JobStub()
        recovery = _RecoveryExecutor()
        scheduler = RetentionScheduler(
            retention_job=job,
            retry_store=retry_store,
            recovery_executor=recovery,
            lease_store=lease,
            interval=timedelta(minutes=1),
            now_factory=lambda: now,
        )

        result = scheduler.tick(batch_size=10)

        self.assertTrue(result.executed)
        self.assertEqual(set(recovery.calls), {"db_mark_failed", "storage_delete_failed"})
        self.assertEqual(retry_store.status_by_id["f-1"], "recovered")
        self.assertEqual(retry_store.status_by_id["f-2"], "retry_scheduled")


if __name__ == "__main__":
    unittest.main()
