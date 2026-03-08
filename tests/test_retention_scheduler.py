from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from evodox.jobs.infrastructure import SQLiteSchedulerLeaseStore
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


class _LeaseWithHeartbeat(InMemorySchedulerLeaseStore):
    def __init__(self) -> None:
        super().__init__()
        self.renewals = 0

    def renew_lock(self, *, now: datetime) -> bool:
        del now
        self.renewals += 1
        return True


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
        self.assertEqual(retry_store.status_by_id[("f-1", "db_mark_failed")], "recovered")
        self.assertEqual(retry_store.status_by_id[("f-2", "storage_delete_failed")], "retry_scheduled")

    def test_scheduler_ignores_manipulated_retry_dataset(self) -> None:
        now = datetime(2026, 3, 8, tzinfo=timezone.utc)
        lease = InMemorySchedulerLeaseStore()
        retry_store = InMemoryRetentionRetryStore(
            [
                RetentionFailureRecord(
                    failure_id="",
                    tenant_id="tenant-a",
                    job_id="job-1",
                    failure_class="db_mark_failed",
                    first_failed_at=now - timedelta(minutes=10),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=0,
                ),
                RetentionFailureRecord(
                    failure_id="f-valid",
                    tenant_id="tenant-a",
                    job_id="job-1",
                    failure_class="storage_delete_failed",
                    first_failed_at=now - timedelta(minutes=10),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=-5,
                ),
            ]
        )
        recovery = _RecoveryExecutor()
        scheduler = RetentionScheduler(
            retention_job=_JobStub(),
            retry_store=retry_store,
            recovery_executor=recovery,
            lease_store=lease,
            interval=timedelta(minutes=1),
            now_factory=lambda: now,
        )

        result = scheduler.tick(batch_size=10)

        self.assertTrue(result.executed)
        self.assertEqual(result.recovered_failures, 0)
        self.assertEqual(recovery.calls, [])
        self.assertEqual(retry_store.status_by_id[("", "db_mark_failed")], "invalid")
        self.assertEqual(retry_store.status_by_id[("f-valid", "storage_delete_failed")], "invalid")

    def test_scheduler_lease_blocks_clock_skew_until_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            t0 = datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)
            fast_clock_now = t0 + timedelta(minutes=2)
            slow_clock_now = t0

            skewed_owner = SQLiteSchedulerLeaseStore(
                db_path,
                lock_owner="sched-fast",
                lease_ttl=timedelta(seconds=30),
            )
            normal_owner = SQLiteSchedulerLeaseStore(
                db_path,
                lock_owner="sched-normal",
                lease_ttl=timedelta(seconds=30),
            )

            self.assertTrue(skewed_owner.should_run(now=fast_clock_now, interval=timedelta(minutes=1)))
            self.assertFalse(normal_owner.should_run(now=slow_clock_now, interval=timedelta(minutes=1)))
            self.assertTrue(normal_owner.should_run(now=fast_clock_now + timedelta(seconds=31), interval=timedelta(minutes=1)))

    def test_scheduler_renews_lease_lock_during_long_due_batch(self) -> None:
        ticks = [
            datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 8, 10, 0, 40, tzinfo=timezone.utc),
            datetime(2026, 3, 8, 10, 1, 20, tzinfo=timezone.utc),
            datetime(2026, 3, 8, 10, 2, 0, tzinfo=timezone.utc),
        ]
        now_iter = iter(ticks)
        lease = _LeaseWithHeartbeat()
        retry_store = InMemoryRetentionRetryStore(
            [
                RetentionFailureRecord(
                    failure_id="f-1",
                    tenant_id="tenant-a",
                    job_id="job-1",
                    failure_class="storage_delete_failed",
                    first_failed_at=ticks[0] - timedelta(minutes=10),
                    next_attempt_at=ticks[0] - timedelta(minutes=1),
                    attempts=0,
                ),
                RetentionFailureRecord(
                    failure_id="f-2",
                    tenant_id="tenant-a",
                    job_id="job-2",
                    failure_class="storage_delete_failed",
                    first_failed_at=ticks[0] - timedelta(minutes=10),
                    next_attempt_at=ticks[0] - timedelta(minutes=1),
                    attempts=0,
                ),
            ]
        )
        scheduler = RetentionScheduler(
            retention_job=_JobStub(),
            retry_store=retry_store,
            recovery_executor=_RecoveryExecutor(),
            lease_store=lease,
            interval=timedelta(minutes=1),
            now_factory=lambda: next(now_iter),
            lease_heartbeat_interval=timedelta(seconds=30),
        )

        result = scheduler.tick(batch_size=10)

        self.assertTrue(result.executed)
        self.assertGreaterEqual(lease.renewals, 1)


if __name__ == "__main__":
    unittest.main()
