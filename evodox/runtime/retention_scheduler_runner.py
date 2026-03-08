from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import signal
import threading
import time
from typing import Any, Callable

from evodox.jobs.infrastructure import (
    JsonlAuditLog,
    SQLiteJobRepository,
    SQLiteRetentionCandidateRepository,
    SQLiteRetentionExecutionRepository,
)
from evodox.jobs.retention_scheduler import RetentionFailureRecord
from evodox.jobs.retention_scheduler_runtime import (
    RetentionSchedulerRuntime,
    RetentionSchedulerRuntimeConfigError,
    RetentionSchedulerRuntimeSettings,
)
from evodox.jobs.retention_service import RetentionEnforcementJob, RetentionPolicyResolver

LOGGER = logging.getLogger("evodox.runtime.retention_scheduler_runner")


@dataclass(frozen=True)
class RetentionSchedulerBootstrapSettings:
    tenant_ids: tuple[str, ...]
    audit_log_path: Path
    object_storage_backend: str = "filesystem"
    object_storage_root: Path | None = None
    s3_bucket: str | None = None
    s3_endpoint: str | None = None
    s3_region: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_force_path_style: bool = True
    policy_min_months: int = 1
    policy_max_months: int = 120
    policy_fallback_months: int = 12
    recovery_mapping_version: str = "v1"

    @classmethod
    def from_env(cls, env: dict[str, str] | None) -> "RetentionSchedulerBootstrapSettings":
        source = env if env is not None else os.environ
        tenant_ids_raw = source.get("RETENTION_TENANT_IDS", "")
        tenant_ids = tuple(item.strip() for item in tenant_ids_raw.split(",") if item.strip())
        if not tenant_ids:
            raise RetentionSchedulerRuntimeConfigError("RETENTION_TENANT_IDS ist erforderlich (CSV).")

        audit_log_path = source.get("RETENTION_AUDIT_LOG_PATH", "").strip()
        if not audit_log_path:
            raise RetentionSchedulerRuntimeConfigError("RETENTION_AUDIT_LOG_PATH ist erforderlich.")

        backend = source.get("RETENTION_OBJECT_STORAGE_BACKEND", "filesystem").strip().lower()
        if backend not in {"filesystem", "s3"}:
            raise RetentionSchedulerRuntimeConfigError(
                "RETENTION_OBJECT_STORAGE_BACKEND muss 'filesystem' oder 's3' sein."
            )

        object_storage_root = None
        s3_bucket = s3_endpoint = s3_region = s3_access_key = s3_secret_key = None
        s3_force_path_style = _parse_bool(source.get("RETENTION_OBJECT_STORAGE_S3_FORCE_PATH_STYLE", "true"))
        if backend == "filesystem":
            root_value = source.get("RETENTION_OBJECT_STORAGE_ROOT", "").strip()
            if not root_value:
                raise RetentionSchedulerRuntimeConfigError("RETENTION_OBJECT_STORAGE_ROOT ist erforderlich.")
            object_storage_root = Path(root_value)
        else:
            s3_bucket = _required_env(source, "RETENTION_OBJECT_STORAGE_S3_BUCKET")
            s3_endpoint = _required_env(source, "RETENTION_OBJECT_STORAGE_S3_ENDPOINT")
            s3_region = _required_env(source, "RETENTION_OBJECT_STORAGE_S3_REGION")
            s3_access_key = _required_env(source, "RETENTION_OBJECT_STORAGE_S3_ACCESS_KEY")
            s3_secret_key = _required_env(source, "RETENTION_OBJECT_STORAGE_S3_SECRET_KEY")

        min_months = _parse_positive_int(source.get("RETENTION_POLICY_MIN_MONTHS", "1"), "RETENTION_POLICY_MIN_MONTHS")
        max_months = _parse_positive_int(source.get("RETENTION_POLICY_MAX_MONTHS", "120"), "RETENTION_POLICY_MAX_MONTHS")
        fallback_months = _parse_positive_int(
            source.get("RETENTION_POLICY_FALLBACK_MONTHS", "12"),
            "RETENTION_POLICY_FALLBACK_MONTHS",
        )

        if max_months < min_months:
            raise RetentionSchedulerRuntimeConfigError(
                "RETENTION_POLICY_MAX_MONTHS muss >= RETENTION_POLICY_MIN_MONTHS sein."
            )
        if not (min_months <= fallback_months <= max_months):
            raise RetentionSchedulerRuntimeConfigError(
                "RETENTION_POLICY_FALLBACK_MONTHS muss zwischen MIN und MAX liegen."
            )

        mapping_version = source.get("RETENTION_RECOVERY_MAPPING_VERSION", "v1").strip().lower()
        if mapping_version != "v1":
            raise RetentionSchedulerRuntimeConfigError("RETENTION_RECOVERY_MAPPING_VERSION muss aktuell 'v1' sein.")

        return cls(
            tenant_ids=tenant_ids,
            audit_log_path=Path(audit_log_path),
            object_storage_backend=backend,
            object_storage_root=object_storage_root,
            s3_bucket=s3_bucket,
            s3_endpoint=s3_endpoint,
            s3_region=s3_region,
            s3_access_key=s3_access_key,
            s3_secret_key=s3_secret_key,
            s3_force_path_style=s3_force_path_style,
            policy_min_months=min_months,
            policy_max_months=max_months,
            policy_fallback_months=fallback_months,
            recovery_mapping_version=mapping_version,
        )


@dataclass(frozen=True)
class RecoveryFailureClassMapping:
    version: str
    handlers: dict[str, str]

    @classmethod
    def v1(cls) -> "RecoveryFailureClassMapping":
        return cls(
            version="v1",
            handlers={
                "storage_delete_failed": "retry_storage_then_mark",
                "db_mark_failed": "retry_mark_only",
            },
        )


class LocalFilesystemRetentionObjectStorage:
    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def delete_prefix(self, *, tenant_id: str, object_prefix: str) -> bool:
        safe_tenant = tenant_id.strip()
        safe_prefix = _sanitize_prefix(object_prefix)
        if not safe_tenant or safe_prefix is None:
            return False

        candidate = self.root / safe_prefix
        resolved_root = self.root.resolve()
        try:
            resolved_candidate = candidate.resolve(strict=False)
        except RuntimeError:
            return False

        if resolved_root not in [resolved_candidate, *resolved_candidate.parents]:
            return False
        if not resolved_candidate.exists():
            return True
        if resolved_candidate.is_file():
            resolved_candidate.unlink()
            return True

        shutil.rmtree(resolved_candidate)
        return True


class S3RetentionObjectStorage:
    def __init__(self, *, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self.client = client

    def delete_prefix(self, *, tenant_id: str, object_prefix: str) -> bool:
        safe_tenant = tenant_id.strip()
        safe_prefix = _sanitize_prefix(object_prefix)
        if not safe_tenant or safe_prefix is None:
            return False

        continuation_token: str | None = None
        while True:
            kwargs = {
                "Bucket": self.bucket,
                "Prefix": safe_prefix,
                "MaxKeys": 1000,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            page = self.client.list_objects_v2(**kwargs)
            contents = page.get("Contents", [])
            if contents:
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": item["Key"]} for item in contents]},
                )
            if not page.get("IsTruncated"):
                break
            continuation_token = page.get("NextContinuationToken")

        return True


class RetentionRecoveryExecutor:
    def __init__(
        self,
        *,
        execution_repository: Any,
        job_repository: Any,
        mapping: RecoveryFailureClassMapping,
    ) -> None:
        self.execution_repository = execution_repository
        self.job_repository = job_repository
        self.mapping = mapping

    def retry(self, record: RetentionFailureRecord) -> bool:
        if not record.tenant_id.strip() or not record.job_id.strip():
            return False

        if self._already_deleted(record):
            return True

        action = self.mapping.handlers.get(record.failure_class)
        if action == "retry_storage_then_mark":
            return self._retry_storage_then_mark(record)
        if action == "retry_mark_only":
            return self._retry_mark_only(record)

        LOGGER.warning(
            "retention_scheduler.runner.recovery_failure_class_unknown",
            extra={"event": {"failure_class": record.failure_class, "mapping_version": self.mapping.version}},
        )
        return False

    def _retry_storage_then_mark(self, record: RetentionFailureRecord) -> bool:
        storage_deleted = self.execution_repository.delete_storage(
            tenant_id=record.tenant_id,
            job_id=record.job_id,
        )
        if not storage_deleted:
            return False
        return self.execution_repository.mark_deleted(
            tenant_id=record.tenant_id,
            job_id=record.job_id,
            deleted_at=datetime.now(tz=timezone.utc),
        )

    def _retry_mark_only(self, record: RetentionFailureRecord) -> bool:
        return self.execution_repository.mark_deleted(
            tenant_id=record.tenant_id,
            job_id=record.job_id,
            deleted_at=datetime.now(tz=timezone.utc),
        )

    def _already_deleted(self, record: RetentionFailureRecord) -> bool:
        job = self.job_repository.get(record.tenant_id, record.job_id)
        if not job:
            return False
        return bool(job.get("deleted_at")) or job.get("status") == "deleted"


@dataclass
class RetentionSchedulerRunner:
    runtime: Any
    settings: RetentionSchedulerRuntimeSettings
    stop_event: threading.Event
    sleep_fn: Callable[[int], None]
    logger: logging.Logger

    def run_forever(self, *, max_ticks: int | None = None) -> int:
        ticks = 0
        while not self.stop_event.is_set():
            try:
                result = self.runtime.run_once()
            except Exception:
                self.logger.exception("retention_scheduler.runner.tick_failed")
            else:
                self.logger.info(
                    "retention_scheduler.runner.tick_completed",
                    extra={
                        "event": {
                            "executed": bool(getattr(result, "executed", True)),
                            "recovered_failures": int(getattr(result, "recovered_failures", 0)),
                        }
                    },
                )

            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            if self.stop_event.is_set():
                break
            self.sleep_fn(self.settings.interval_seconds)

        self.logger.info("retention_scheduler.runner.stopped")
        return 0


def create_retention_scheduler_runner(
    *,
    env: dict[str, str] | None,
    retention_job: Any,
    recovery_executor: Any,
    runtime_factory: Callable[..., Any] = RetentionSchedulerRuntime,
    stop_event: threading.Event | None = None,
    signal_module: Any = signal,
    sleep_fn: Callable[[int], None] = time.sleep,
    logger: logging.Logger = LOGGER,
) -> RetentionSchedulerRunner:
    settings = RetentionSchedulerRuntimeSettings.from_env(env)
    runtime = runtime_factory(
        settings=settings,
        retention_job=retention_job,
        recovery_executor=recovery_executor,
    )
    shutdown_event = stop_event or threading.Event()
    _install_signal_handlers(shutdown_event, signal_module=signal_module, logger=logger)

    logger.info(
        "retention_scheduler.runner.started",
        extra={
            "event": {
                "lock_owner": settings.lock_owner,
                "db_path": str(settings.db_path),
                "interval_seconds": settings.interval_seconds,
                "batch_size": settings.batch_size,
                "lease_ttl_seconds": settings.lease_ttl_seconds,
                "lease_heartbeat_seconds": settings.lease_heartbeat_seconds,
            }
        },
    )

    return RetentionSchedulerRunner(
        runtime=runtime,
        settings=settings,
        stop_event=shutdown_event,
        sleep_fn=sleep_fn,
        logger=logger,
    )


def run_retention_scheduler_runner(
    *,
    env: dict[str, str] | None,
    retention_job: Any,
    recovery_executor: Any,
    runtime_factory: Callable[..., Any] = RetentionSchedulerRuntime,
    stop_event: threading.Event | None = None,
    signal_module: Any = signal,
    sleep_fn: Callable[[int], None] = time.sleep,
    logger: logging.Logger = LOGGER,
    max_ticks: int | None = None,
) -> int:
    try:
        runner = create_retention_scheduler_runner(
            env=env,
            retention_job=retention_job,
            recovery_executor=recovery_executor,
            runtime_factory=runtime_factory,
            stop_event=stop_event,
            signal_module=signal_module,
            sleep_fn=sleep_fn,
            logger=logger,
        )
    except RetentionSchedulerRuntimeConfigError as exc:
        logger.error(
            "retention_scheduler.runner.config_error",
            extra={"event": {"error": str(exc)}},
        )
        return 2

    return runner.run_forever(max_ticks=max_ticks)


def build_runtime_dependencies(
    *,
    env: dict[str, str] | None,
    s3_client_factory: Callable[..., Any] | None = None,
) -> tuple[Any, Any]:
    source = env if env is not None else os.environ
    runtime_settings = RetentionSchedulerRuntimeSettings.from_env(source)
    bootstrap_settings = RetentionSchedulerBootstrapSettings.from_env(source)

    tenant_defaults = {
        tenant_id: bootstrap_settings.policy_fallback_months
        for tenant_id in bootstrap_settings.tenant_ids
    }
    policy_resolver = RetentionPolicyResolver(
        global_min_months=bootstrap_settings.policy_min_months,
        global_max_months=bootstrap_settings.policy_max_months,
        tenant_defaults=tenant_defaults,
        fallback_default_months=bootstrap_settings.policy_fallback_months,
    )

    object_storage = _create_object_storage(bootstrap_settings, s3_client_factory=s3_client_factory)
    audit_log = JsonlAuditLog(bootstrap_settings.audit_log_path)
    execution_repository = SQLiteRetentionExecutionRepository(runtime_settings.db_path, object_storage=object_storage)
    candidate_repository = SQLiteRetentionCandidateRepository(runtime_settings.db_path)
    job_repository = SQLiteJobRepository(runtime_settings.db_path)

    retention_job = RetentionEnforcementJob(
        tenant_ids=list(bootstrap_settings.tenant_ids),
        candidate_repository=candidate_repository,
        execution_repository=execution_repository,
        policy_resolver=policy_resolver,
        audit_log=audit_log,
    )
    recovery_executor = RetentionRecoveryExecutor(
        execution_repository=execution_repository,
        job_repository=job_repository,
        mapping=RecoveryFailureClassMapping.v1(),
    )
    return retention_job, recovery_executor


def validate_runner_environment(*, env: dict[str, str] | None) -> list[str]:
    source = env if env is not None else os.environ
    errors: list[str] = []
    try:
        RetentionSchedulerRuntimeSettings.from_env(source)
    except RetentionSchedulerRuntimeConfigError as exc:
        errors.append(str(exc))
    try:
        RetentionSchedulerBootstrapSettings.from_env(source)
    except RetentionSchedulerRuntimeConfigError as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    _configure_logging()
    env = dict(os.environ)
    max_ticks = _parse_optional_int(env.get("RETENTION_SCHEDULER_MAX_TICKS", ""), "RETENTION_SCHEDULER_MAX_TICKS")

    if env.get("RETENTION_VALIDATE_ENV_ONLY", "false").strip().lower() in {"1", "true", "yes", "on"}:
        errors = validate_runner_environment(env=env)
        if errors:
            for error in errors:
                LOGGER.error("retention_scheduler.runner.preflight_error", extra={"event": {"error": error}})
            return 2
        LOGGER.info("retention_scheduler.runner.preflight_ok")
        return 0

    try:
        retention_job, recovery_executor = build_runtime_dependencies(env=env)
    except RetentionSchedulerRuntimeConfigError as exc:
        LOGGER.error("retention_scheduler.runner.config_error", extra={"event": {"error": str(exc)}})
        return 2

    return run_retention_scheduler_runner(
        env=env,
        retention_job=retention_job,
        recovery_executor=recovery_executor,
        max_ticks=max_ticks,
    )


def _create_object_storage(
    settings: RetentionSchedulerBootstrapSettings,
    *,
    s3_client_factory: Callable[..., Any] | None,
) -> Any:
    if settings.object_storage_backend == "filesystem":
        if settings.object_storage_root is None:
            raise RetentionSchedulerRuntimeConfigError("RETENTION_OBJECT_STORAGE_ROOT ist erforderlich.")
        return LocalFilesystemRetentionObjectStorage(root=settings.object_storage_root)

    factory = s3_client_factory or _default_s3_client_factory
    client = factory(
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        force_path_style=settings.s3_force_path_style,
    )
    if settings.s3_bucket is None:
        raise RetentionSchedulerRuntimeConfigError("RETENTION_OBJECT_STORAGE_S3_BUCKET ist erforderlich.")
    return S3RetentionObjectStorage(bucket=settings.s3_bucket, client=client)


def _default_s3_client_factory(
    *,
    endpoint_url: str | None,
    region_name: str | None,
    aws_access_key_id: str | None,
    aws_secret_access_key: str | None,
    force_path_style: bool,
) -> Any:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover
        raise RetentionSchedulerRuntimeConfigError(
            "S3-Backend gewählt, aber boto3 ist nicht installiert."
        ) from exc

    config = None
    if force_path_style:
        try:
            from botocore.config import Config

            config = Config(s3={"addressing_style": "path"})
        except Exception as exc:  # pragma: no cover
            raise RetentionSchedulerRuntimeConfigError("botocore Config konnte nicht geladen werden.") from exc

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        config=config,
    )


def _install_signal_handlers(stop_event: threading.Event, *, signal_module: Any, logger: logging.Logger) -> None:
    def _handle_shutdown(signum: int, _frame: Any) -> None:
        logger.info("retention_scheduler.runner.shutdown_requested", extra={"event": {"signal": signum}})
        stop_event.set()

    signal_module.signal(signal_module.SIGTERM, _handle_shutdown)
    signal_module.signal(signal_module.SIGINT, _handle_shutdown)


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("RETENTION_RUNNER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _parse_positive_int(raw: str, key: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise RetentionSchedulerRuntimeConfigError(f"{key} muss eine Zahl sein.") from exc
    if value <= 0:
        raise RetentionSchedulerRuntimeConfigError(f"{key} muss > 0 sein.")
    return value


def _parse_optional_int(raw: str, key: str) -> int | None:
    value = raw.strip()
    if not value:
        return None
    return _parse_positive_int(value, key)


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    return value in {"1", "true", "yes", "on"}


def _required_env(source: dict[str, str], key: str) -> str:
    value = source.get(key, "").strip()
    if not value:
        raise RetentionSchedulerRuntimeConfigError(f"{key} ist erforderlich.")
    return value


def _sanitize_prefix(raw_prefix: str) -> str | None:
    safe_prefix = raw_prefix.strip().replace("\\", "/")
    if not safe_prefix.startswith("tenant/"):
        return None
    if ".." in safe_prefix:
        return None
    return safe_prefix


if __name__ == "__main__":
    raise SystemExit(main())
