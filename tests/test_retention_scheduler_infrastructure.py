from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from evodox.jobs.infrastructure import SQLiteRetentionRetryStore, SQLiteSchedulerLeaseStore
from evodox.jobs.retention_scheduler import RetentionFailureRecord, RetentionScheduler


class _JobStub:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, *, batch_size: int) -> None:
        del batch_size
        self.calls += 1


class _DeterministicRecovery:
    def __init__(self, *, succeed_failure_classes: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.succeed_failure_classes = succeed_failure_classes or set()

    def retry(self, record: RetentionFailureRecord) -> bool:
        self.calls.append((record.failure_id, record.failure_class))
        return record.failure_class in self.succeed_failure_classes


class RetentionSchedulerInfrastructureTests(unittest.TestCase):
    def test_scheduler_lease_persists_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            now = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            job = _JobStub()
            retry = SQLiteRetentionRetryStore(db_path)

            scheduler_1 = RetentionScheduler(
                retention_job=job,
                retry_store=retry,
                recovery_executor=_DeterministicRecovery(),
                lease_store=SQLiteSchedulerLeaseStore(db_path, lock_owner="p1"),
                interval=timedelta(minutes=30),
                now_factory=lambda: now,
            )
            first = scheduler_1.tick(batch_size=10)

            scheduler_2 = RetentionScheduler(
                retention_job=job,
                retry_store=retry,
                recovery_executor=_DeterministicRecovery(),
                lease_store=SQLiteSchedulerLeaseStore(db_path, lock_owner="p2"),
                interval=timedelta(minutes=30),
                now_factory=lambda: now + timedelta(minutes=5),
            )
            second = scheduler_2.tick(batch_size=10)

            self.assertTrue(first.executed)
            self.assertFalse(second.executed)
            self.assertEqual(job.calls, 1)

    def test_competing_schedulers_collide_on_same_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            now = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            owner_a = SQLiteSchedulerLeaseStore(db_path, lock_owner="a", lease_ttl=timedelta(minutes=2))
            owner_b = SQLiteSchedulerLeaseStore(db_path, lock_owner="b", lease_ttl=timedelta(minutes=2))

            got_a = owner_a.should_run(now=now, interval=timedelta(minutes=1))
            got_b = owner_b.should_run(now=now, interval=timedelta(minutes=1))

            self.assertTrue(got_a)
            self.assertFalse(got_b)

            owner_a.mark_ran(now=now)
            self.assertFalse(owner_b.should_run(now=now + timedelta(seconds=10), interval=timedelta(minutes=1)))
            self.assertTrue(owner_b.should_run(now=now + timedelta(minutes=2), interval=timedelta(minutes=1)))

    def test_recovery_continues_after_partial_failure_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            now = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            retry_store = SQLiteRetentionRetryStore(db_path)
            retry_store.upsert_failure(
                RetentionFailureRecord(
                    failure_id="f1",
                    tenant_id="tenant-a",
                    job_id="job-1",
                    failure_class="db_mark_failed",
                    first_failed_at=now - timedelta(minutes=10),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=0,
                )
            )
            retry_store.upsert_failure(
                RetentionFailureRecord(
                    failure_id="f2",
                    tenant_id="tenant-a",
                    job_id="job-2",
                    failure_class="storage_delete_failed",
                    first_failed_at=now - timedelta(minutes=10),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=0,
                )
            )

            recovery_1 = _DeterministicRecovery(succeed_failure_classes={"db_mark_failed"})
            scheduler_1 = RetentionScheduler(
                retention_job=_JobStub(),
                retry_store=retry_store,
                recovery_executor=recovery_1,
                lease_store=SQLiteSchedulerLeaseStore(db_path, lock_owner="p1"),
                interval=timedelta(minutes=1),
                now_factory=lambda: now,
            )
            scheduler_1.tick(batch_size=10)

            due_after_first = retry_store.list_due(now=now + timedelta(minutes=1), limit=10)
            self.assertEqual({(r.failure_id, r.failure_class) for r in due_after_first}, set())

            recovery_2 = _DeterministicRecovery(succeed_failure_classes={"storage_delete_failed"})
            scheduler_2 = RetentionScheduler(
                retention_job=_JobStub(),
                retry_store=retry_store,
                recovery_executor=recovery_2,
                lease_store=SQLiteSchedulerLeaseStore(db_path, lock_owner="p2"),
                interval=timedelta(minutes=1),
                now_factory=lambda: now + timedelta(minutes=6),
            )
            result = scheduler_2.tick(batch_size=10)

            self.assertTrue(result.executed)
            self.assertEqual(result.recovered_failures, 1)
            self.assertEqual(recovery_2.calls, [("f2", "storage_delete_failed")])


if __name__ == "__main__":
    unittest.main()
