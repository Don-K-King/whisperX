from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class JobStatusResponse:
    job_id: str
    status: str
    progress: int
    retention_until: str


class JobStatusNotFoundError(Exception):
    def __init__(self):
        self.error_code = "job.not_found"
        super().__init__("Job not found")


class InMemoryJobStatusStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    def add(self, item: dict[str, Any]) -> None:
        self._items[(item["tenant_id"], item["job_id"])] = dict(item)

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        row = self._items.get((tenant_id, job_id))
        return None if row is None else dict(row)


def get_job_status(*, job_id: str, tenant_id: str, job_store: Any) -> JobStatusResponse:
    row = job_store.get(tenant_id, job_id)
    if row is None:
        raise JobStatusNotFoundError()

    status = str(row.get("status", "created"))
    progress = _derive_progress(status=status, raw_progress=row.get("progress"))
    retention_until = _derive_retention_until(
        created_at=str(row.get("created_at") or datetime.now(tz=timezone.utc).isoformat()),
        retention_months=int(row.get("retention_months", 12)),
    )
    return JobStatusResponse(
        job_id=job_id,
        status=status,
        progress=progress,
        retention_until=retention_until,
    )


def _derive_progress(*, status: str, raw_progress: Any) -> int:
    if isinstance(raw_progress, int):
        return max(0, min(100, raw_progress))
    if status == "completed":
        return 100
    return 0


def _derive_retention_until(*, created_at: str, retention_months: int) -> str:
    base = _parse_iso_datetime(created_at)
    # bewusst einfach und deterministisch (30-Tage-Monate) bis kalendarischer Dienst eingeführt wird
    retention_days = max(1, retention_months) * 30
    return (base + timedelta(days=retention_days)).isoformat()


def _parse_iso_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.now(tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
