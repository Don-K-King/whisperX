from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import os
from pathlib import Path
from typing import Any

from .infrastructure import SQLiteRetentionRetryStore, SQLiteSchedulerLeaseStore
from .retention_scheduler import RetentionScheduler


class RetentionSchedulerRuntimeConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RetentionSchedulerRuntimeSettings:
    db_path: Path
    lock_owner: str
    interval_seconds: int = 300
    batch_size: int = 100
    lease_ttl_seconds: int = 300
    lease_heartbeat_seconds: int = 60

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "RetentionSchedulerRuntimeSettings":
        source = env if env is not None else os.environ
        db_path = source.get("RETENTION_DB_PATH", "").strip()
        lock_owner = source.get("RETENTION_SCHEDULER_LOCK_OWNER", "").strip()
        interval = source.get("RETENTION_SCHEDULER_INTERVAL_SECONDS", "300")
        batch_size = source.get("RETENTION_SCHEDULER_BATCH_SIZE", "100")
        lease_ttl = source.get("RETENTION_SCHEDULER_LEASE_TTL_SECONDS", "300")
        lease_heartbeat = source.get("RETENTION_SCHEDULER_HEARTBEAT_SECONDS", "60")

        if not db_path:
            raise RetentionSchedulerRuntimeConfigError("RETENTION_DB_PATH ist erforderlich.")
        if not lock_owner:
            raise RetentionSchedulerRuntimeConfigError("RETENTION_SCHEDULER_LOCK_OWNER ist erforderlich.")

        interval_seconds = _parse_positive_int(interval, "RETENTION_SCHEDULER_INTERVAL_SECONDS")
        batch_size_value = _parse_positive_int(batch_size, "RETENTION_SCHEDULER_BATCH_SIZE")
        lease_ttl_seconds = _parse_positive_int(lease_ttl, "RETENTION_SCHEDULER_LEASE_TTL_SECONDS")
        lease_heartbeat_seconds = _parse_positive_int(lease_heartbeat, "RETENTION_SCHEDULER_HEARTBEAT_SECONDS")

        if lease_heartbeat_seconds >= lease_ttl_seconds:
            raise RetentionSchedulerRuntimeConfigError(
                "RETENTION_SCHEDULER_HEARTBEAT_SECONDS muss kleiner als RETENTION_SCHEDULER_LEASE_TTL_SECONDS sein."
            )

        return cls(
            db_path=Path(db_path),
            lock_owner=lock_owner,
            interval_seconds=interval_seconds,
            batch_size=batch_size_value,
            lease_ttl_seconds=lease_ttl_seconds,
            lease_heartbeat_seconds=lease_heartbeat_seconds,
        )


class RetentionSchedulerRuntime:
    def __init__(
        self,
        *,
        settings: RetentionSchedulerRuntimeSettings,
        retention_job: Any,
        recovery_executor: Any,
        now_factory: Any | None = None,
    ) -> None:
        self.settings = settings
        self.scheduler = RetentionScheduler(
            retention_job=retention_job,
            retry_store=SQLiteRetentionRetryStore(settings.db_path),
            recovery_executor=recovery_executor,
            lease_store=SQLiteSchedulerLeaseStore(
                settings.db_path,
                lock_owner=settings.lock_owner,
                lease_ttl=timedelta(seconds=settings.lease_ttl_seconds),
            ),
            interval=timedelta(seconds=settings.interval_seconds),
            now_factory=now_factory,
            lease_heartbeat_interval=timedelta(seconds=settings.lease_heartbeat_seconds),
        )

    def run_once(self) -> Any:
        return self.scheduler.tick(batch_size=self.settings.batch_size)


def _parse_positive_int(raw: str, key: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise RetentionSchedulerRuntimeConfigError(f"{key} muss eine Zahl sein.") from exc
    if value <= 0:
        raise RetentionSchedulerRuntimeConfigError(f"{key} muss > 0 sein.")
    return value
