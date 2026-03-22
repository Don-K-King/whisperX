from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from evodox.jobs.infrastructure import SQLiteRetentionRetryStore, SQLiteSchedulerLeaseStore
from evodox.jobs.retention_scheduler import RetentionFailureRecord
from evodox.jobs.retention_scheduler_runtime import (
    RetentionSchedulerRuntime,
    RetentionSchedulerRuntimeConfigError,
    RetentionSchedulerRuntimeSettings,
)


class _JobStub:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, *, batch_size: int) -> None:
        del batch_size
        self.calls += 1


class _RecoveryExecutor:
    def __init__(self, *, succeed_failure_classes: set[str] | None = None) -> None:
        self.succeed_failure_classes = succeed_failure_classes or set()

    def retry(self, record: RetentionFailureRecord) -> bool:
        return record.failure_class in self.succeed_failure_classes


class RetentionSchedulerRuntimeTests(unittest.TestCase):
    def test_settings_from_env_requires_mandatory_keys(self) -> None:
        with self.assertRaises(RetentionSchedulerRuntimeConfigError):
            RetentionSchedulerRuntimeSettings.from_env({})

    def test_settings_from_env_rejects_invalid_heartbeat_ratio(self) -> None:
        with self.assertRaises(RetentionSchedulerRuntimeConfigError):
            RetentionSchedulerRuntimeSettings.from_env(
                {
                    "RETENTION_DB_PATH": "/tmp/jobs.db",
                    "RETENTION_SCHEDULER_LOCK_OWNER": "worker-a",
                    "RETENTION_SCHEDULER_LEASE_TTL_SECONDS": "30",
                    "RETENTION_SCHEDULER_HEARTBEAT_SECONDS": "30",
                }
            )

    def test_runtime_wires_sqlite_stores_and_persists_schedule_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            settings_a = RetentionSchedulerRuntimeSettings(
                db_path=db_path,
                lock_owner="node-a",
                interval_seconds=120,
                batch_size=20,
                lease_ttl_seconds=120,
                lease_heartbeat_seconds=30,
            )
            t0 = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            job = _JobStub()
            runtime_a = RetentionSchedulerRuntime(
                settings=settings_a,
                retention_job=job,
                recovery_executor=_RecoveryExecutor(),
                now_factory=lambda: t0,
            )

            self.assertIsInstance(runtime_a.scheduler.retry_store, SQLiteRetentionRetryStore)
            self.assertIsInstance(runtime_a.scheduler.lease_store, SQLiteSchedulerLeaseStore)

            first = runtime_a.run_once()
            self.assertTrue(first.executed)

            settings_b = RetentionSchedulerRuntimeSettings(
                db_path=db_path,
                lock_owner="node-b",
                interval_seconds=120,
                batch_size=20,
                lease_ttl_seconds=120,
                lease_heartbeat_seconds=30,
            )
            runtime_b = RetentionSchedulerRuntime(
                settings=settings_b,
                retention_job=job,
                recovery_executor=_RecoveryExecutor(),
                now_factory=lambda: t0 + timedelta(seconds=30),
            )
            second = runtime_b.run_once()

            self.assertFalse(second.executed)
            self.assertEqual(job.calls, 1)


if __name__ == "__main__":
    unittest.main()
