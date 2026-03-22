from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest

from evodox.jobs.infrastructure import SQLiteRetentionRetryStore, SQLiteSchedulerLeaseStore
from evodox.jobs.retention_scheduler import RetentionFailureRecord
from evodox.jobs.retention_scheduler_runtime import RetentionSchedulerRuntimeConfigError
from evodox.runtime.retention_scheduler_runner import (
    LocalFilesystemRetentionObjectStorage,
    RecoveryFailureClassMapping,
    RetentionRecoveryExecutor,
    S3RetentionObjectStorage,
    build_runtime_dependencies,
    create_retention_scheduler_runner,
    run_retention_scheduler_runner,
    validate_runner_environment,
)


class _NoopRetentionJob:
    def run(self, *, batch_size: int) -> None:
        del batch_size


class _NoopRecoveryExecutor:
    def retry(self, record):
        del record
        return True


class _RuntimeSpy:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return {"executed": True}


class _SignalModuleStub:
    SIGTERM = 15
    SIGINT = 2

    def __init__(self) -> None:
        self.handlers = {}

    def signal(self, signum, handler):
        self.handlers[signum] = handler


class _ExecutionRepositoryStub:
    def __init__(self) -> None:
        self.storage_calls = 0
        self.mark_calls = 0

    def delete_storage(self, *, tenant_id: str, job_id: str) -> bool:
        del tenant_id, job_id
        self.storage_calls += 1
        return True

    def mark_deleted(self, *, tenant_id: str, job_id: str, deleted_at: datetime) -> bool:
        del tenant_id, job_id, deleted_at
        self.mark_calls += 1
        return True


class _JobRepositoryStub:
    def __init__(self, *, deleted: bool = False) -> None:
        self.deleted = deleted

    def get(self, tenant_id: str, job_id: str):
        del tenant_id, job_id
        if self.deleted:
            return {"status": "deleted", "deleted_at": datetime.now(tz=timezone.utc).isoformat()}
        return None


class _S3ClientStub:
    def __init__(self, *, pages: list[dict] | None = None) -> None:
        self.pages = list(pages or [])
        self.delete_calls: list[dict] = []
        self.list_calls: list[dict] = []

    def list_objects_v2(self, **kwargs):
        self.list_calls.append(kwargs)
        if self.pages:
            return self.pages.pop(0)
        return {"Contents": []}

    def delete_objects(self, **kwargs):
        self.delete_calls.append(kwargs)
        return {"Deleted": kwargs.get("Delete", {}).get("Objects", [])}


class RetentionSchedulerRunnerTests(unittest.TestCase):
    def test_start_with_valid_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "RETENTION_DB_PATH": str(Path(tmpdir) / "jobs.db"),
                "RETENTION_SCHEDULER_LOCK_OWNER": "runner-a",
                "RETENTION_SCHEDULER_INTERVAL_SECONDS": "1",
                "RETENTION_SCHEDULER_BATCH_SIZE": "10",
                "RETENTION_SCHEDULER_LEASE_TTL_SECONDS": "90",
                "RETENTION_SCHEDULER_HEARTBEAT_SECONDS": "30",
            }

            code = run_retention_scheduler_runner(
                env=env,
                retention_job=_NoopRetentionJob(),
                recovery_executor=_NoopRecoveryExecutor(),
                max_ticks=1,
            )

            self.assertEqual(code, 0)

    def test_start_fails_fast_on_invalid_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "RETENTION_DB_PATH": str(Path(tmpdir) / "jobs.db"),
                "RETENTION_SCHEDULER_INTERVAL_SECONDS": "1",
            }

            code = run_retention_scheduler_runner(
                env=env,
                retention_job=_NoopRetentionJob(),
                recovery_executor=_NoopRecoveryExecutor(),
            )

            self.assertNotEqual(code, 0)

    def test_shutdown_signal_stops_runner_without_second_tick(self) -> None:
        runtime = _RuntimeSpy()
        stop_event = threading.Event()
        signal_module = _SignalModuleStub()

        def sleep_fn(_: int) -> None:
            signal_module.handlers[signal_module.SIGTERM](signal_module.SIGTERM, None)

        runner = create_retention_scheduler_runner(
            env={
                "RETENTION_DB_PATH": "/tmp/retention-runner.db",
                "RETENTION_SCHEDULER_LOCK_OWNER": "runner-a",
                "RETENTION_SCHEDULER_INTERVAL_SECONDS": "5",
            },
            retention_job=_NoopRetentionJob(),
            recovery_executor=_NoopRecoveryExecutor(),
            runtime_factory=lambda **_: runtime,
            stop_event=stop_event,
            signal_module=signal_module,
            sleep_fn=sleep_fn,
        )

        runner.run_forever()

        self.assertTrue(stop_event.is_set())
        self.assertEqual(runtime.calls, 1)

    def test_runner_uses_sqlite_stores_not_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = create_retention_scheduler_runner(
                env={
                    "RETENTION_DB_PATH": str(Path(tmpdir) / "jobs.db"),
                    "RETENTION_SCHEDULER_LOCK_OWNER": "runner-a",
                },
                retention_job=_NoopRetentionJob(),
                recovery_executor=_NoopRecoveryExecutor(),
            )

            self.assertIsInstance(runner.runtime.scheduler.retry_store, SQLiteRetentionRetryStore)
            self.assertIsInstance(runner.runtime.scheduler.lease_store, SQLiteSchedulerLeaseStore)

    def test_build_runtime_dependencies_fails_without_bootstrap_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RetentionSchedulerRuntimeConfigError):
                build_runtime_dependencies(
                    env={
                        "RETENTION_DB_PATH": str(Path(tmpdir) / "jobs.db"),
                        "RETENTION_SCHEDULER_LOCK_OWNER": "runner-a",
                    }
                )

    def test_build_runtime_dependencies_with_valid_filesystem_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "RETENTION_DB_PATH": str(Path(tmpdir) / "jobs.db"),
                "RETENTION_SCHEDULER_LOCK_OWNER": "runner-a",
                "RETENTION_TENANT_IDS": "tenant-a,tenant-b",
                "RETENTION_AUDIT_LOG_PATH": str(Path(tmpdir) / "audit.jsonl"),
                "RETENTION_OBJECT_STORAGE_BACKEND": "filesystem",
                "RETENTION_OBJECT_STORAGE_ROOT": str(Path(tmpdir) / "objects"),
            }

            retention_job, recovery_executor = build_runtime_dependencies(env=env)

            self.assertIsNotNone(retention_job)
            self.assertIsNotNone(recovery_executor)

    def test_build_runtime_dependencies_with_valid_s3_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "RETENTION_DB_PATH": str(Path(tmpdir) / "jobs.db"),
                "RETENTION_SCHEDULER_LOCK_OWNER": "runner-a",
                "RETENTION_TENANT_IDS": "tenant-a,tenant-b",
                "RETENTION_AUDIT_LOG_PATH": str(Path(tmpdir) / "audit.jsonl"),
                "RETENTION_OBJECT_STORAGE_BACKEND": "s3",
                "RETENTION_OBJECT_STORAGE_S3_BUCKET": "jobs-bucket",
                "RETENTION_OBJECT_STORAGE_S3_ENDPOINT": "http://localhost:9000",
                "RETENTION_OBJECT_STORAGE_S3_REGION": "us-east-1",
                "RETENTION_OBJECT_STORAGE_S3_ACCESS_KEY": "access",
                "RETENTION_OBJECT_STORAGE_S3_SECRET_KEY": "secret",
                "RETENTION_OBJECT_STORAGE_S3_FORCE_PATH_STYLE": "true",
            }

            retention_job, recovery_executor = build_runtime_dependencies(env=env, s3_client_factory=lambda **_: _S3ClientStub())

            self.assertIsNotNone(retention_job)
            self.assertIsNotNone(recovery_executor)

    def test_local_filesystem_storage_blocks_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "objects"
            storage = LocalFilesystemRetentionObjectStorage(root=root)
            outside = Path(tmpdir) / "outside.txt"
            outside.write_text("secret", encoding="utf-8")

            deleted = storage.delete_prefix(tenant_id="tenant-a", object_prefix="tenant/../../outside.txt")

            self.assertFalse(deleted)
            self.assertTrue(outside.exists())

    def test_s3_storage_uses_prefix_delete_semantics(self) -> None:
        client = _S3ClientStub(
            pages=[
                {
                    "Contents": [
                        {"Key": "tenant/tenant-a/job-1/a.wav"},
                        {"Key": "tenant/tenant-a/job-1/b.json"},
                    ],
                    "IsTruncated": False,
                }
            ]
        )
        storage = S3RetentionObjectStorage(bucket="jobs", client=client)

        deleted = storage.delete_prefix(tenant_id="tenant-a", object_prefix="tenant/tenant-a/job-1/")

        self.assertTrue(deleted)
        self.assertEqual(len(client.delete_calls), 1)
        deleted_keys = client.delete_calls[0]["Delete"]["Objects"]
        self.assertEqual(deleted_keys, [{"Key": "tenant/tenant-a/job-1/a.wav"}, {"Key": "tenant/tenant-a/job-1/b.json"}])

    def test_s3_storage_rejects_traversal_prefix(self) -> None:
        client = _S3ClientStub()
        storage = S3RetentionObjectStorage(bucket="jobs", client=client)

        deleted = storage.delete_prefix(tenant_id="tenant-a", object_prefix="tenant/../../bad")

        self.assertFalse(deleted)
        self.assertEqual(client.delete_calls, [])
        self.assertEqual(client.list_calls, [])

    def test_recovery_executor_marks_deleted_as_recovered(self) -> None:
        executor = RetentionRecoveryExecutor(
            execution_repository=_ExecutionRepositoryStub(),
            job_repository=_JobRepositoryStub(deleted=True),
            mapping=RecoveryFailureClassMapping.v1(),
        )
        record = RetentionFailureRecord(
            failure_id="f-1",
            tenant_id="tenant-a",
            job_id="job-1",
            failure_class="db_mark_failed",
            first_failed_at=datetime.now(tz=timezone.utc),
            next_attempt_at=datetime.now(tz=timezone.utc),
            attempts=1,
        )

        ok = executor.retry(record)

        self.assertTrue(ok)

    def test_recovery_executor_handles_storage_failure_class(self) -> None:
        execution_repo = _ExecutionRepositoryStub()
        executor = RetentionRecoveryExecutor(
            execution_repository=execution_repo,
            job_repository=_JobRepositoryStub(deleted=False),
            mapping=RecoveryFailureClassMapping.v1(),
        )
        record = RetentionFailureRecord(
            failure_id="f-2",
            tenant_id="tenant-a",
            job_id="job-2",
            failure_class="storage_delete_failed",
            first_failed_at=datetime.now(tz=timezone.utc),
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(minutes=1),
            attempts=2,
        )

        ok = executor.retry(record)

        self.assertTrue(ok)
        self.assertEqual(execution_repo.storage_calls, 1)
        self.assertEqual(execution_repo.mark_calls, 1)

    def test_recovery_executor_unknown_class_is_fail_safe(self) -> None:
        execution_repo = _ExecutionRepositoryStub()
        executor = RetentionRecoveryExecutor(
            execution_repository=execution_repo,
            job_repository=_JobRepositoryStub(deleted=False),
            mapping=RecoveryFailureClassMapping.v1(),
        )
        record = RetentionFailureRecord(
            failure_id="f-3",
            tenant_id="tenant-a",
            job_id="job-3",
            failure_class="unknown_class",
            first_failed_at=datetime.now(tz=timezone.utc),
            next_attempt_at=datetime.now(tz=timezone.utc),
            attempts=1,
        )

        ok = executor.retry(record)

        self.assertFalse(ok)
        self.assertEqual(execution_repo.storage_calls, 0)
        self.assertEqual(execution_repo.mark_calls, 0)

    def test_validate_runner_environment_reports_errors(self) -> None:
        errors = validate_runner_environment(env={})

        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
