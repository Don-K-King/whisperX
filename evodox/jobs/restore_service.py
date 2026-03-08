from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

RESTORE_TABLE_ORDER = [
    "jobs",
    "transcripts",
    "transcript_versions",
    "export_artifacts",
    "audit_events",
]


@dataclass(frozen=True)
class RestoreExecutionInput:
    tenant_id: str
    backup_id: str
    tables: list[str]
    object_keys: list[str]


@dataclass(frozen=True)
class ConsistencyIssue:
    error_code: str
    message: str
    resource_type: str
    resource_id: str


@dataclass(frozen=True)
class RestoreExecutionResult:
    status: str
    restored_tables: list[str]
    restored_objects: int
    consistency_issues: list[ConsistencyIssue]


class RestoreValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class RestoreConsistencyChecker:
    def __init__(self, graph_repository: Any) -> None:
        self.graph_repository = graph_repository

    def check(self, *, tenant_id: str) -> list[ConsistencyIssue]:
        jobs = set(self.graph_repository.list_job_ids(tenant_id=tenant_id))
        issues: list[ConsistencyIssue] = []

        for job_id in self.graph_repository.list_transcript_job_links(tenant_id=tenant_id):
            if job_id not in jobs:
                issues.append(
                    ConsistencyIssue(
                        error_code="restore.consistency.missing_job_reference",
                        message="Transcript verweist auf nicht vorhandenen Job.",
                        resource_type="transcript",
                        resource_id=job_id,
                    )
                )

        for job_id in self.graph_repository.list_export_job_links(tenant_id=tenant_id):
            if job_id not in jobs:
                issues.append(
                    ConsistencyIssue(
                        error_code="restore.consistency.missing_job_reference",
                        message="Export verweist auf nicht vorhandenen Job.",
                        resource_type="export_artifact",
                        resource_id=job_id,
                    )
                )

        for job_id in self.graph_repository.list_audit_job_links(tenant_id=tenant_id):
            if job_id not in jobs:
                issues.append(
                    ConsistencyIssue(
                        error_code="restore.consistency.missing_job_reference",
                        message="Audit-Eintrag verweist auf nicht vorhandenen Job.",
                        resource_type="audit_event",
                        resource_id=job_id,
                    )
                )

        return issues


def execute_restore(
    request: RestoreExecutionInput,
    *,
    tenant_id: str,
    actor_id: str,
    restore_repository: Any,
    graph_repository: Any,
    audit_log: Any,
) -> RestoreExecutionResult:
    _validate_request(request=request, tenant_id=tenant_id)
    checker = RestoreConsistencyChecker(graph_repository)

    _audit_append(
        audit_log,
        {
            "action": "restore.started",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "backup_id": request.backup_id,
            "tables": list(request.tables),
            "object_count": len(request.object_keys),
        },
    )

    restored_tables: list[str] = []
    for table in _sort_tables(request.tables):
        restore_repository.restore_table(tenant_id=tenant_id, backup_id=request.backup_id, table_name=table)
        restored_tables.append(table)

    for object_key in request.object_keys:
        restore_repository.restore_object(tenant_id=tenant_id, backup_id=request.backup_id, object_key=object_key)

    consistency_issues = checker.check(tenant_id=tenant_id)
    status = "completed" if len(consistency_issues) == 0 else "completed_with_findings"

    _audit_append(
        audit_log,
        {
            "action": "restore.completed",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "backup_id": request.backup_id,
            "status": status,
            "restored_tables": restored_tables,
            "restored_objects": len(request.object_keys),
            "consistency_issue_count": len(consistency_issues),
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        },
    )

    return RestoreExecutionResult(
        status=status,
        restored_tables=restored_tables,
        restored_objects=len(request.object_keys),
        consistency_issues=consistency_issues,
    )


def _validate_request(*, request: RestoreExecutionInput, tenant_id: str) -> None:
    if request.tenant_id != tenant_id:
        raise RestoreValidationError("restore.tenant_mismatch", "Restore darf nur im eigenen Tenant-Kontext laufen.")
    if not isinstance(request.backup_id, str) or len(request.backup_id.strip()) < 3:
        raise RestoreValidationError("restore.invalid_backup_id", "backup_id ist erforderlich.")
    if len(request.tables) == 0:
        raise RestoreValidationError("restore.invalid_tables", "Mindestens eine Tabelle muss wiederhergestellt werden.")
    for table in request.tables:
        if table not in RESTORE_TABLE_ORDER:
            raise RestoreValidationError("restore.invalid_table", f"Unbekannte Tabelle: {table}")
    for object_key in request.object_keys:
        if not object_key.startswith(f"tenant/{tenant_id}/"):
            raise RestoreValidationError(
                "restore.object_scope_invalid",
                "Object-Key liegt außerhalb des Tenant-Scope.",
            )


def _sort_tables(tables: list[str]) -> list[str]:
    unique = list(dict.fromkeys(tables))
    position = {name: idx for idx, name in enumerate(RESTORE_TABLE_ORDER)}
    return sorted(unique, key=lambda t: position[t])


class InMemoryRestoreRepository:
    def __init__(self) -> None:
        self.table_restores: list[tuple[str, str, str]] = []
        self.object_restores: list[tuple[str, str, str]] = []

    def restore_table(self, *, tenant_id: str, backup_id: str, table_name: str) -> None:
        self.table_restores.append((tenant_id, backup_id, table_name))

    def restore_object(self, *, tenant_id: str, backup_id: str, object_key: str) -> None:
        self.object_restores.append((tenant_id, backup_id, object_key))


class InMemoryTenantGraphRepository:
    def __init__(
        self,
        *,
        jobs: set[str] | None = None,
        transcript_job_links: set[str] | None = None,
        export_job_links: set[str] | None = None,
        audit_job_links: set[str] | None = None,
    ) -> None:
        self.jobs = jobs or set()
        self.transcript_job_links = transcript_job_links or set()
        self.export_job_links = export_job_links or set()
        self.audit_job_links = audit_job_links or set()

    def list_job_ids(self, *, tenant_id: str) -> list[str]:
        del tenant_id
        return sorted(self.jobs)

    def list_transcript_job_links(self, *, tenant_id: str) -> list[str]:
        del tenant_id
        return sorted(self.transcript_job_links)

    def list_export_job_links(self, *, tenant_id: str) -> list[str]:
        del tenant_id
        return sorted(self.export_job_links)

    def list_audit_job_links(self, *, tenant_id: str) -> list[str]:
        del tenant_id
        return sorted(self.audit_job_links)


class InMemoryRestoreAuditLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, payload: dict[str, Any]) -> None:
        self.events.append(payload)


def _audit_append(audit_log: Any, payload: dict[str, Any]) -> None:
    if hasattr(audit_log, "append"):
        audit_log.append(payload)
        return
    if isinstance(audit_log, list):
        audit_log.append(payload)
