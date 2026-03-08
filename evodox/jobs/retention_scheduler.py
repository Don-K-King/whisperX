from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class RetentionFailureRecord:
    failure_id: str
    tenant_id: str
    job_id: str
    failure_class: str
    first_failed_at: datetime
    next_attempt_at: datetime
    attempts: int


@dataclass(frozen=True)
class RetentionSchedulerTickResult:
    executed: bool
    recovered_failures: int


class RetentionScheduler:
    def __init__(
        self,
        *,
        retention_job: Any,
        retry_store: Any,
        recovery_executor: Any,
        lease_store: Any,
        interval: timedelta,
        now_factory: Any | None = None,
    ) -> None:
        self.retention_job = retention_job
        self.retry_store = retry_store
        self.recovery_executor = recovery_executor
        self.lease_store = lease_store
        self.interval = interval
        self.now_factory = now_factory or (lambda: datetime.now(tz=timezone.utc))

    def tick(self, *, batch_size: int = 100) -> RetentionSchedulerTickResult:
        now = self.now_factory()
        if not self.lease_store.should_run(now=now, interval=self.interval):
            return RetentionSchedulerTickResult(executed=False, recovered_failures=0)

        self.retention_job.run(batch_size=batch_size)

        recovered = 0
        for failure in self.retry_store.list_due(now=now, limit=batch_size):
            ok = self.recovery_executor.retry(failure)
            if ok:
                self.retry_store.mark_recovered(failure.failure_id)
                recovered += 1
            else:
                self.retry_store.mark_retry_scheduled(failure.failure_id, next_attempt_at=now + timedelta(minutes=5))

        self.lease_store.mark_ran(now=now)
        return RetentionSchedulerTickResult(executed=True, recovered_failures=recovered)


class InMemorySchedulerLeaseStore:
    def __init__(self) -> None:
        self.last_run_at: datetime | None = None

    def should_run(self, *, now: datetime, interval: timedelta) -> bool:
        if self.last_run_at is None:
            return True
        return now >= self.last_run_at + interval

    def mark_ran(self, *, now: datetime) -> None:
        self.last_run_at = now


class InMemoryRetentionRetryStore:
    def __init__(self, records: list[RetentionFailureRecord] | None = None) -> None:
        self.records = {record.failure_id: record for record in (records or [])}
        self.status_by_id = {record.failure_id: "pending" for record in (records or [])}

    def list_due(self, *, now: datetime, limit: int) -> list[RetentionFailureRecord]:
        due = [
            r
            for r in self.records.values()
            if self.status_by_id.get(r.failure_id, "pending") in {"pending", "retry_scheduled"}
            and r.next_attempt_at <= now
        ]
        due.sort(key=lambda r: (r.next_attempt_at, r.failure_id))
        return due[:limit]

    def mark_recovered(self, failure_id: str) -> None:
        self.status_by_id[failure_id] = "recovered"

    def mark_retry_scheduled(self, failure_id: str, *, next_attempt_at: datetime) -> None:
        current = self.records[failure_id]
        self.records[failure_id] = RetentionFailureRecord(
            failure_id=current.failure_id,
            tenant_id=current.tenant_id,
            job_id=current.job_id,
            failure_class=current.failure_class,
            first_failed_at=current.first_failed_at,
            next_attempt_at=next_attempt_at,
            attempts=current.attempts + 1,
        )
        self.status_by_id[failure_id] = "retry_scheduled"
