from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class ResolvedRetentionPolicy:
    tenant_id: str
    months: int
    source: str
    reason: str | None = None


class RetentionPolicyInputError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class RetentionPolicyResolver:
    def __init__(
        self,
        *,
        global_min_months: int,
        global_max_months: int,
        tenant_defaults: dict[str, int],
        fallback_default_months: int = 12,
    ) -> None:
        if global_min_months < 1 or global_max_months < global_min_months:
            raise ValueError("invalid retention bounds")
        self.global_min_months = global_min_months
        self.global_max_months = global_max_months
        self.tenant_defaults = dict(tenant_defaults)
        self.fallback_default_months = fallback_default_months

    def resolve(self, *, tenant_id: str, requested_months: int | None) -> ResolvedRetentionPolicy:
        if not isinstance(tenant_id, str) or tenant_id.strip() == "":
            raise RetentionPolicyInputError("retention.invalid_tenant", "tenant_id is required")

        if requested_months is None:
            base = self.tenant_defaults.get(tenant_id, self.fallback_default_months)
            source = "tenant_default" if tenant_id in self.tenant_defaults else "system_default"
        else:
            if not isinstance(requested_months, int):
                raise RetentionPolicyInputError(
                    "retention.invalid_requested_months", "requested retention must be an integer"
                )
            base = requested_months
            source = "request"

        if base < self.global_min_months:
            return ResolvedRetentionPolicy(
                tenant_id=tenant_id,
                months=self.global_min_months,
                source=source,
                reason="clamped_to_min",
            )
        if base > self.global_max_months:
            return ResolvedRetentionPolicy(
                tenant_id=tenant_id,
                months=self.global_max_months,
                source=source,
                reason="clamped_to_max",
            )
        return ResolvedRetentionPolicy(tenant_id=tenant_id, months=base, source=source)


@dataclass(frozen=True)
class RetentionCandidate:
    tenant_id: str
    job_id: str
    requested_retention_months: int | None
    created_at: datetime


@dataclass(frozen=True)
class RetentionRunSummary:
    processed: int
    deleted: int
    skipped: int
    failed: int


class RetentionEnforcementJob:
    def __init__(
        self,
        *,
        tenant_ids: list[str],
        candidate_repository: Any,
        execution_repository: Any,
        policy_resolver: RetentionPolicyResolver,
        audit_log: Any,
        now_factory: Any | None = None,
        clock_skew_tolerance: timedelta = timedelta(minutes=5),
    ) -> None:
        self.tenant_ids = list(tenant_ids)
        self.candidate_repository = candidate_repository
        self.execution_repository = execution_repository
        self.policy_resolver = policy_resolver
        self.audit_log = audit_log
        self.now_factory = now_factory or (lambda: datetime.now(tz=timezone.utc))
        self.clock_skew_tolerance = clock_skew_tolerance

    def run(self, *, batch_size: int = 100) -> RetentionRunSummary:
        now = self.now_factory()
        processed = deleted = skipped = failed = 0

        for tenant_id in self.tenant_ids:
            candidates = self.candidate_repository.list_due_for_tenant(
                tenant_id=tenant_id,
                now=now,
                limit=batch_size,
            )
            for candidate in candidates:
                processed += 1
                outcome = self._process_candidate(now=now, candidate=candidate)
                if outcome == "deleted":
                    deleted += 1
                elif outcome == "skipped":
                    skipped += 1
                else:
                    failed += 1

        return RetentionRunSummary(processed=processed, deleted=deleted, skipped=skipped, failed=failed)

    def _process_candidate(self, *, now: datetime, candidate: RetentionCandidate) -> str:
        policy = self.policy_resolver.resolve(
            tenant_id=candidate.tenant_id,
            requested_months=candidate.requested_retention_months,
        )
        retention_until = candidate.created_at + timedelta(days=policy.months * 30)

        if now < retention_until + self.clock_skew_tolerance:
            _audit_append(
                self.audit_log,
                {
                    "action": "retention.decision",
                    "tenant_id": candidate.tenant_id,
                    "job_id": candidate.job_id,
                    "decision": "skip_clock_skew",
                    "retention_until": retention_until.isoformat(),
                    "policy_source": policy.source,
                    "policy_months": policy.months,
                },
            )
            return "skipped"

        _audit_append(
            self.audit_log,
            {
                "action": "retention.decision",
                "tenant_id": candidate.tenant_id,
                "job_id": candidate.job_id,
                "decision": "delete",
                "retention_until": retention_until.isoformat(),
                "policy_source": policy.source,
                "policy_months": policy.months,
                "policy_reason": policy.reason,
            },
        )

        storage_deleted = self.execution_repository.delete_storage(
            tenant_id=candidate.tenant_id,
            job_id=candidate.job_id,
        )
        db_marked = self.execution_repository.mark_deleted(
            tenant_id=candidate.tenant_id,
            job_id=candidate.job_id,
            deleted_at=now,
        )

        if storage_deleted and db_marked:
            _audit_append(
                self.audit_log,
                {
                    "action": "retention.execution",
                    "tenant_id": candidate.tenant_id,
                    "job_id": candidate.job_id,
                    "storage_deleted": True,
                    "db_marked": True,
                    "ts": now.isoformat(),
                },
            )
            return "deleted"

        _audit_append(
            self.audit_log,
            {
                "action": "retention.execution.failed",
                "tenant_id": candidate.tenant_id,
                "job_id": candidate.job_id,
                "storage_deleted": storage_deleted,
                "db_marked": db_marked,
                "ts": now.isoformat(),
            },
        )
        return "failed"


class InMemoryRetentionCandidateRepository:
    def __init__(self, items_by_tenant: dict[str, list[RetentionCandidate]]):
        self._items_by_tenant = {
            tenant: list(items)
            for tenant, items in items_by_tenant.items()
        }
        self.calls: list[tuple[str, datetime, int]] = []

    def list_due_for_tenant(self, *, tenant_id: str, now: datetime, limit: int) -> list[RetentionCandidate]:
        self.calls.append((tenant_id, now, limit))
        items = self._items_by_tenant.get(tenant_id, [])
        return [item for item in items if item.created_at <= now][:limit]


class InMemoryRetentionExecutionRepository:
    def __init__(self, *, fail_storage_for: set[str] | None = None, fail_db_for: set[str] | None = None):
        self.fail_storage_for = fail_storage_for or set()
        self.fail_db_for = fail_db_for or set()
        self.deletions: list[tuple[str, str]] = []
        self.db_marks: list[tuple[str, str, datetime]] = []

    def delete_storage(self, *, tenant_id: str, job_id: str) -> bool:
        self.deletions.append((tenant_id, job_id))
        return job_id not in self.fail_storage_for

    def mark_deleted(self, *, tenant_id: str, job_id: str, deleted_at: datetime) -> bool:
        self.db_marks.append((tenant_id, job_id, deleted_at))
        return job_id not in self.fail_db_for


class InMemoryRetentionAuditLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event: dict[str, Any]) -> None:
        self.events.append(event)


def _audit_append(audit_log: Any, payload: dict[str, Any]) -> None:
    if hasattr(audit_log, "append"):
        audit_log.append(payload)
        return
    if isinstance(audit_log, list):
        audit_log.append(payload)
