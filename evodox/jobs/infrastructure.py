from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
import random
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlencode

from .complete_upload_service import CompleteUploadIdempotencyRecord, CompleteUploadResponse
from .create_service import CreateJobResponse, IdempotencyRecord, UploadSession
from .retention_scheduler import RetentionFailureRecord
from .retention_service import RetentionCandidate
from .transcript_service import TranscriptConflictError, TranscriptResponse, TranscriptValidationError


class SQLiteJobRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    retention_months INTEGER NOT NULL,
                    upload_session_id TEXT,
                    object_key TEXT,
                    checksum_sha256 TEXT,
                    progress INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "deleted_at" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN deleted_at TEXT")
            if "upload_session_id" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN upload_session_id TEXT")
            if "object_key" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN object_key TEXT")
            if "checksum_sha256" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN checksum_sha256 TEXT")
            if "progress" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN progress INTEGER")

    def create(self, job: Any) -> None:
        payload = _to_dict(job)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, tenant_id, actor_id, filename, content_type, size_bytes, retention_months,
                    upload_session_id, object_key, checksum_sha256, progress, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["job_id"],
                    payload["tenant_id"],
                    payload["actor_id"],
                    payload["filename"],
                    payload["content_type"],
                    int(payload["size_bytes"]),
                    int(payload["retention_months"]),
                    payload.get("upload_session_id"),
                    payload.get("object_key"),
                    payload.get("checksum_sha256"),
                    payload.get("progress"),
                    payload["status"],
                ),
            )

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE tenant_id = ? AND job_id = ?",
                (tenant_id, job_id),
            ).fetchone()
        return None if row is None else dict(row)

    def set_status(self, tenant_id: str, job_id: str, status: str, *, progress: int | None = None) -> None:
        with self._connect() as conn:
            if progress is None:
                updated = conn.execute(
                    "UPDATE jobs SET status = ? WHERE tenant_id = ? AND job_id = ?",
                    (status, tenant_id, job_id),
                )
            else:
                updated = conn.execute(
                    "UPDATE jobs SET status = ?, progress = ? WHERE tenant_id = ? AND job_id = ?",
                    (status, int(progress), tenant_id, job_id),
                )
        if updated.rowcount == 0:
            raise KeyError("job not found")

    def mark_queued(
        self,
        tenant_id: str,
        job_id: str,
        *,
        object_key: str,
        checksum_sha256: str,
        upload_session_id: str,
    ) -> None:
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = 'queued',
                    upload_session_id = ?,
                    object_key = ?,
                    checksum_sha256 = ?,
                    progress = 5
                WHERE tenant_id = ? AND job_id = ?
                """,
                (upload_session_id, object_key, checksum_sha256, tenant_id, job_id),
            )
        if updated.rowcount == 0:
            raise KeyError("job not found")

    def list_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE tenant_id = ? AND deleted_at IS NULL ORDER BY created_at",
                (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_queued_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_deleted(self, tenant_id: str, job_id: str, *, actor_id: str) -> None:
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = 'deleted',
                    progress = 100,
                    actor_id = ?,
                    filename = '[redacted]',
                    deleted_at = ?
                WHERE tenant_id = ? AND job_id = ? AND deleted_at IS NULL
                """,
                (actor_id, datetime.now(tz=timezone.utc).isoformat(), tenant_id, job_id),
            )
        if updated.rowcount == 0:
            raise KeyError("job not found")


class SQLiteRetentionCandidateRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_due_for_tenant(self, *, tenant_id: str, now: datetime, limit: int) -> list[RetentionCandidate]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tenant_id, job_id, retention_months, created_at
                FROM jobs
                WHERE tenant_id = ?
                  AND deleted_at IS NULL
                  AND datetime(created_at, printf('+%d days', retention_months * 30)) <= datetime(?)
                ORDER BY created_at
                LIMIT ?
                """,
                (tenant_id, now.isoformat(), limit),
            ).fetchall()
        return [
            RetentionCandidate(
                tenant_id=row["tenant_id"],
                job_id=row["job_id"],
                requested_retention_months=int(row["retention_months"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]


class SQLiteRetentionExecutionRepository:
    def __init__(self, db_path: Path, *, object_storage: Any) -> None:
        self._db_path = str(db_path)
        self.object_storage = object_storage

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def delete_storage(self, *, tenant_id: str, job_id: str) -> bool:
        object_prefix = f"tenant/{tenant_id}/{job_id}/"
        if not hasattr(self.object_storage, "delete_prefix"):
            return False
        return bool(self.object_storage.delete_prefix(tenant_id=tenant_id, object_prefix=object_prefix))

    def mark_deleted(self, *, tenant_id: str, job_id: str, deleted_at: datetime) -> bool:
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = 'deleted',
                    filename = '[redacted]',
                    actor_id = 'retention-worker',
                    deleted_at = ?
                WHERE tenant_id = ? AND job_id = ? AND deleted_at IS NULL
                """,
                (deleted_at.isoformat(), tenant_id, job_id),
            )
            conn.execute(
                "DELETE FROM outbox_events WHERE tenant_id = ? AND job_id = ?",
                (tenant_id, job_id),
            )
        return updated.rowcount == 1


class SQLiteSchedulerLeaseStore:
    def __init__(
        self,
        db_path: Path,
        *,
        lease_name: str = "retention_scheduler",
        lock_owner: str,
        lease_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self._db_path = str(db_path)
        self.lease_name = lease_name
        self.lock_owner = lock_owner
        self.lease_ttl = lease_ttl
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_leases (
                    lease_name TEXT PRIMARY KEY,
                    last_run_at TEXT,
                    lock_owner TEXT,
                    lock_until TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO scheduler_leases (lease_name, last_run_at, lock_owner, lock_until)
                VALUES (?, NULL, NULL, NULL)
                """,
                (self.lease_name,),
            )

    def should_run(self, *, now: datetime, interval: timedelta) -> bool:
        now_iso = now.isoformat()
        lock_until_iso = (now + self.lease_ttl).isoformat()
        interval_seconds = int(interval.total_seconds())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_run_at, lock_owner, lock_until FROM scheduler_leases WHERE lease_name = ?",
                (self.lease_name,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO scheduler_leases (lease_name, last_run_at, lock_owner, lock_until) VALUES (?, NULL, NULL, NULL)",
                    (self.lease_name,),
                )
                row = conn.execute(
                    "SELECT last_run_at, lock_owner, lock_until FROM scheduler_leases WHERE lease_name = ?",
                    (self.lease_name,),
                ).fetchone()

            due = row["last_run_at"] is None or bool(
                conn.execute(
                    "SELECT datetime(?) >= datetime(?, printf('+%d seconds', ?))",
                    (now_iso, row["last_run_at"], interval_seconds),
                ).fetchone()[0]
            )
            lease_free = row["lock_until"] is None or bool(
                conn.execute("SELECT datetime(?) >= datetime(?)", (now_iso, row["lock_until"])).fetchone()[0]
            )
            lease_owned = row["lock_owner"] == self.lock_owner

            if not due or not (lease_free or lease_owned):
                return False

            updated = conn.execute(
                """
                UPDATE scheduler_leases
                SET lock_owner = ?,
                    lock_until = ?
                WHERE lease_name = ?
                  AND (lock_until IS NULL OR datetime(lock_until) <= datetime(?) OR lock_owner = ?)
                """,
                (self.lock_owner, lock_until_iso, self.lease_name, now_iso, self.lock_owner),
            )
        return updated.rowcount == 1

    def mark_ran(self, *, now: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scheduler_leases
                SET last_run_at = ?,
                    lock_owner = NULL,
                    lock_until = NULL
                WHERE lease_name = ? AND lock_owner = ?
                """,
                (now.isoformat(), self.lease_name, self.lock_owner),
            )

    def renew_lock(self, *, now: datetime) -> bool:
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE scheduler_leases
                SET lock_until = ?
                WHERE lease_name = ? AND lock_owner = ?
                """,
                ((now + self.lease_ttl).isoformat(), self.lease_name, self.lock_owner),
            )
        return updated.rowcount == 1


class SQLiteRetentionRetryStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS retention_retry_queue (
                    failure_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    failure_class TEXT NOT NULL,
                    first_failed_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    invalid_reason TEXT,
                    PRIMARY KEY (failure_id, failure_class)
                )
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(retention_retry_queue)").fetchall()
            }
            if "invalid_reason" not in columns:
                conn.execute("ALTER TABLE retention_retry_queue ADD COLUMN invalid_reason TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_retention_retry_tenant_id ON retention_retry_queue(tenant_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_retention_retry_status_due ON retention_retry_queue(status, next_attempt_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_retention_retry_next_attempt_at ON retention_retry_queue(next_attempt_at)"
            )

    def upsert_failure(self, record: RetentionFailureRecord, *, status: str = "pending") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO retention_retry_queue (
                    failure_id, tenant_id, job_id, failure_class, first_failed_at, attempts, next_attempt_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(failure_id, failure_class)
                DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    job_id = excluded.job_id,
                    first_failed_at = excluded.first_failed_at,
                    attempts = CASE
                        WHEN retention_retry_queue.status = 'recovered' THEN retention_retry_queue.attempts
                        ELSE excluded.attempts
                    END,
                    next_attempt_at = CASE
                        WHEN retention_retry_queue.status = 'recovered' THEN retention_retry_queue.next_attempt_at
                        ELSE excluded.next_attempt_at
                    END,
                    status = CASE
                        WHEN retention_retry_queue.status = 'recovered' THEN retention_retry_queue.status
                        ELSE excluded.status
                    END
                """,
                (
                    record.failure_id,
                    record.tenant_id,
                    record.job_id,
                    record.failure_class,
                    record.first_failed_at.isoformat(),
                    int(record.attempts),
                    record.next_attempt_at.isoformat(),
                    status,
                ),
            )

    def list_due(self, *, now: datetime, limit: int) -> list[RetentionFailureRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT failure_id, tenant_id, job_id, failure_class, first_failed_at, attempts, next_attempt_at
                FROM retention_retry_queue
                WHERE status IN ('pending', 'retry_scheduled')
                  AND datetime(next_attempt_at) <= datetime(?)
                ORDER BY datetime(next_attempt_at) ASC, failure_id ASC
                LIMIT ?
                """,
                (now.isoformat(), limit),
            ).fetchall()
        return [
            RetentionFailureRecord(
                failure_id=row["failure_id"],
                tenant_id=row["tenant_id"],
                job_id=row["job_id"],
                failure_class=row["failure_class"],
                first_failed_at=datetime.fromisoformat(row["first_failed_at"]),
                next_attempt_at=datetime.fromisoformat(row["next_attempt_at"]),
                attempts=int(row["attempts"]),
            )
            for row in rows
        ]

    def mark_recovered(self, failure_id: str, *, failure_class: str | None = None) -> None:
        if failure_class is None:
            raise ValueError("failure_class ist erforderlich, um idempotente Recovery eindeutig zu adressieren.")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE retention_retry_queue
                SET status = 'recovered',
                    invalid_reason = NULL
                WHERE failure_id = ? AND failure_class = ?
                """,
                (failure_id, failure_class),
            )

    def mark_retry_scheduled(
        self,
        failure_id: str,
        *,
        failure_class: str | None = None,
        next_attempt_at: datetime,
    ) -> None:
        if failure_class is None:
            raise ValueError("failure_class ist erforderlich, um idempotente Retry-Planung eindeutig zu adressieren.")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE retention_retry_queue
                SET status = 'retry_scheduled',
                    attempts = attempts + 1,
                    next_attempt_at = ?,
                    invalid_reason = NULL
                WHERE failure_id = ? AND failure_class = ?
                """,
                (next_attempt_at.isoformat(), failure_id, failure_class),
            )

    def mark_invalid(self, failure_id: str, *, failure_class: str | None = None, reason: str) -> None:
        if failure_class is None:
            raise ValueError("failure_class ist erforderlich, um invalid records eindeutig zu adressieren.")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE retention_retry_queue
                SET status = 'invalid',
                    invalid_reason = ?
                WHERE failure_id = ? AND failure_class = ?
                """,
                (reason, failure_id, failure_class),
            )


class InMemoryRetentionObjectStorage:
    def __init__(self, *, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        self.deleted_prefixes: list[tuple[str, str]] = []

    def delete_prefix(self, *, tenant_id: str, object_prefix: str) -> bool:
        self.deleted_prefixes.append((tenant_id, object_prefix))
        return object_prefix not in self.fail_for


class SQLiteIdempotencyStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_records (
                    tenant_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, idempotency_key)
                )
                """
            )

    def get(self, tenant_id: str, key: str) -> IdempotencyRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_hash, response_json FROM idempotency_records WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, key),
            ).fetchone()
        if row is None:
            return None
        response_payload = json.loads(row["response_json"])
        upload = UploadSession(**response_payload["upload"])
        response = CreateJobResponse(
            job_id=response_payload["job_id"],
            tenant_id=response_payload["tenant_id"],
            status=response_payload["status"],
            upload=upload,
        )
        return IdempotencyRecord(tenant_id=tenant_id, payload_hash=row["payload_hash"], response=response)

    def put(self, tenant_id: str, key: str, record: IdempotencyRecord) -> None:
        response_json = json.dumps(_response_to_dict(record.response), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO idempotency_records (tenant_id, idempotency_key, payload_hash, response_json)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, key, record.payload_hash, response_json),
            )


class SQLiteCompleteUploadIdempotencyStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS complete_upload_idempotency (
                    tenant_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, idempotency_key)
                )
                """
            )

    def get(self, tenant_id: str, key: str) -> CompleteUploadIdempotencyRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_hash, response_json FROM complete_upload_idempotency WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, key),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["response_json"])
        response = CompleteUploadResponse(
            job_id=payload["job_id"],
            status=payload["status"],
            queue=payload["queue"],
        )
        return CompleteUploadIdempotencyRecord(tenant_id=tenant_id, payload_hash=row["payload_hash"], response=response)

    def put(self, tenant_id: str, key: str, record: CompleteUploadIdempotencyRecord) -> None:
        payload = {"job_id": record.response.job_id, "status": record.response.status, "queue": record.response.queue}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO complete_upload_idempotency (tenant_id, idempotency_key, payload_hash, response_json)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, key, record.payload_hash, json.dumps(payload, sort_keys=True)),
            )


class SQLiteOutbox:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_uid TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    queue TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error_code TEXT,
                    last_error_class TEXT,
                    dlq_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    published_at TEXT,
                    dlq_at TEXT,
                    publish_attempted_at TEXT,
                    UNIQUE(event_uid)
                )
                """
            )
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(outbox_events)").fetchall()
            }
            _add_column_if_missing(conn, columns, "event_uid", "TEXT")
            _add_column_if_missing(conn, columns, "retry_count", "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_missing(conn, columns, "next_attempt_at", "TEXT")
            _add_column_if_missing(conn, columns, "last_error_code", "TEXT")
            _add_column_if_missing(conn, columns, "last_error_class", "TEXT")
            _add_column_if_missing(conn, columns, "dlq_reason", "TEXT")
            _add_column_if_missing(conn, columns, "dlq_at", "TEXT")
            _add_column_if_missing(conn, columns, "publish_attempted_at", "TEXT")

    def append(self, event: dict[str, Any]) -> None:
        event_uid = event.get("event_id") or _stable_event_uid(event)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO outbox_events (event_uid, event_type, tenant_id, job_id, queue, payload_json, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    event_uid,
                    event["event_type"],
                    event["tenant_id"],
                    event["job_id"],
                    event["queue"],
                    json.dumps(event, sort_keys=True),
                ),
            )

    def list_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox_events WHERE status = 'pending' ORDER BY event_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_uid": row["event_uid"],
                "event_type": row["event_type"],
                "tenant_id": row["tenant_id"],
                "job_id": row["job_id"],
                "queue": row["queue"],
                "retry_count": int(row["retry_count"] or 0),
                "next_attempt_at": row["next_attempt_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def list_dlq(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox_events WHERE status = 'dlq' ORDER BY event_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_uid": row["event_uid"],
                "event_type": row["event_type"],
                "tenant_id": row["tenant_id"],
                "job_id": row["job_id"],
                "queue": row["queue"],
                "retry_count": int(row["retry_count"] or 0),
                "last_error_code": row["last_error_code"],
                "last_error_class": row["last_error_class"],
                "dlq_reason": row["dlq_reason"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def mark_published(self, event_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE outbox_events SET status = 'published', published_at = ?, publish_attempted_at = ?, next_attempt_at = NULL WHERE event_id = ?",
                (datetime.now(tz=timezone.utc).isoformat(), datetime.now(tz=timezone.utc).isoformat(), event_id),
            )

    def mark_duplicate(self, event_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE outbox_events SET status = 'published', published_at = ?, publish_attempted_at = ?, last_error_code = 'duplicate.delivery', last_error_class = 'duplicate', next_attempt_at = NULL WHERE event_id = ?",
                (
                    datetime.now(tz=timezone.utc).isoformat(),
                    datetime.now(tz=timezone.utc).isoformat(),
                    event_id,
                ),
            )

    def mark_retry(self, event_id: int, *, error_code: str, next_attempt_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox_events
                SET retry_count = retry_count + 1,
                    last_error_code = ?,
                    last_error_class = 'retryable',
                    publish_attempted_at = ?,
                    next_attempt_at = ?
                WHERE event_id = ?
                """,
                (error_code, datetime.now(tz=timezone.utc).isoformat(), next_attempt_at.isoformat(), event_id),
            )

    def mark_dlq(self, event_id: int, *, reason: str, error_code: str, error_class: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox_events
                SET status = 'dlq',
                    dlq_reason = ?,
                    last_error_code = ?,
                    last_error_class = ?,
                    dlq_at = ?,
                    publish_attempted_at = ?,
                    next_attempt_at = NULL
                WHERE event_id = ?
                """,
                (
                    reason,
                    error_code,
                    error_class,
                    datetime.now(tz=timezone.utc).isoformat(),
                    datetime.now(tz=timezone.utc).isoformat(),
                    event_id,
                ),
            )

    def prune_pending_for_job(
        self,
        *,
        tenant_id: str,
        job_id: str,
        error_code: str = "job.deleted",
        error_class: str = "skipped",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox_events
                SET status = 'published',
                    published_at = ?,
                    publish_attempted_at = ?,
                    next_attempt_at = NULL,
                    last_error_code = ?,
                    last_error_class = ?
                WHERE tenant_id = ? AND job_id = ? AND status = 'pending'
                """,
                (
                    datetime.now(tz=timezone.utc).isoformat(),
                    datetime.now(tz=timezone.utc).isoformat(),
                    error_code,
                    error_class,
                    tenant_id,
                    job_id,
                ),
            )


class RetryablePublishError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


class TerminalPublishError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


class DuplicateDeliveryError(Exception):
    def __init__(self, error_code: str = "duplicate.delivery"):
        self.error_code = error_code
        super().__init__(error_code)


class InMemoryQueueDispatchMetrics:
    def __init__(self) -> None:
        self.published_count = 0
        self.retry_count = 0
        self.dlq_count = 0
        self.duplicate_count = 0
        self.queue_lag: list[float] = []

    def record_published(self) -> None:
        self.published_count += 1

    def record_retry(self) -> None:
        self.retry_count += 1

    def record_dlq(self) -> None:
        self.dlq_count += 1

    def record_duplicate(self) -> None:
        self.duplicate_count += 1

    def record_queue_lag_seconds(self, lag_seconds: float) -> None:
        self.queue_lag.append(max(0.0, lag_seconds))


class OutboxQueueDispatcher:
    def __init__(
        self,
        *,
        outbox: SQLiteOutbox,
        queue_publisher: Any,
        max_retries: int = 5,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
        jitter_factory: Any | None = None,
        now_factory: Any | None = None,
        metrics: Any | None = None,
    ) -> None:
        self.outbox = outbox
        self.queue_publisher = queue_publisher
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.jitter_factory = jitter_factory or random.uniform
        self.now_factory = now_factory or (lambda: datetime.now(tz=timezone.utc))
        self.metrics = metrics

    def dispatch_pending(self, *, limit: int = 100) -> int:
        published = 0
        for event in self.outbox.list_pending(limit=limit):
            if not _is_due(event.get("next_attempt_at"), now=self.now_factory()):
                continue
            self._record_queue_lag(event)
            try:
                self.queue_publisher.publish(
                    event["queue"],
                    event["payload"],
                    message_id=event["event_uid"],
                    headers={"tenant_id": event["tenant_id"], "event_type": event["event_type"]},
                )
                self.outbox.mark_published(event["event_id"])
                _metric(self.metrics, "record_published")
                published += 1
            except DuplicateDeliveryError:
                self.outbox.mark_duplicate(event["event_id"])
                _metric(self.metrics, "record_duplicate")
            except RetryablePublishError as exc:
                if event.get("retry_count", 0) + 1 > self.max_retries:
                    self.outbox.mark_dlq(
                        event["event_id"],
                        reason="retry_exhausted",
                        error_code=exc.error_code,
                        error_class="retryable",
                    )
                    _metric(self.metrics, "record_dlq")
                    continue
                next_attempt_at = self.now_factory() + timedelta(
                    seconds=self._calculate_backoff(event.get("retry_count", 0))
                )
                self.outbox.mark_retry(event["event_id"], error_code=exc.error_code, next_attempt_at=next_attempt_at)
                _metric(self.metrics, "record_retry")
            except TerminalPublishError as exc:
                self.outbox.mark_dlq(
                    event["event_id"],
                    reason="terminal_publish_error",
                    error_code=exc.error_code,
                    error_class="terminal",
                )
                _metric(self.metrics, "record_dlq")
        return published

    def _calculate_backoff(self, retry_count: int) -> float:
        upper = min(self.max_backoff_seconds, self.base_backoff_seconds * (2**retry_count))
        return float(self.jitter_factory(0.0, upper))

    def _record_queue_lag(self, event: dict[str, Any]) -> None:
        created_at = event.get("payload", {}).get("timestamp")
        if not isinstance(created_at, str):
            return
        try:
            ts = datetime.fromisoformat(created_at)
        except ValueError:
            return
        lag = (self.now_factory() - ts).total_seconds()
        if self.metrics is not None:
            self.metrics.record_queue_lag_seconds(lag)


class InMemoryQueuePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def publish(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        message_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        del message_id, headers
        self.messages.append((queue_name, dict(payload)))


class RabbitMQQueuePublisher:
    def __init__(self, *, amqp_url: str, exchange: str = "evodox.jobs") -> None:
        self.amqp_url = amqp_url
        self.exchange = exchange

    def publish(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        message_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        try:
            import pika
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("RabbitMQ Publisher benötigt das Paket 'pika'.") from exc
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        properties = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
            message_id=message_id,
            headers=headers or {},
        )
        connection = None
        try:
            params = pika.URLParameters(self.amqp_url)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.exchange_declare(exchange=self.exchange, exchange_type="direct", durable=True)
            channel.queue_declare(queue=queue_name, durable=True)
            channel.queue_bind(queue=queue_name, exchange=self.exchange, routing_key=queue_name)
            published = channel.basic_publish(
                exchange=self.exchange,
                routing_key=queue_name,
                body=body,
                properties=properties,
                mandatory=True,
            )
            if not published:
                raise RetryablePublishError("broker.publish_not_confirmed")
        except RetryablePublishError:
            raise
        except Exception as exc:
            raise RetryablePublishError("broker.unavailable") from exc
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass


def _add_column_if_missing(conn: sqlite3.Connection, columns: set[str], column_name: str, ddl: str) -> None:
    if column_name in columns:
        return
    conn.execute(f"ALTER TABLE outbox_events ADD COLUMN {column_name} {ddl}")


def _stable_event_uid(event: dict[str, Any]) -> str:
    canonical = json.dumps(event, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metric(metrics: Any, method: str) -> None:
    if metrics is None:
        return
    recorder = getattr(metrics, method, None)
    if recorder is None:
        return
    recorder()


def _is_due(next_attempt_at: str | None, *, now: datetime) -> bool:
    if not next_attempt_at:
        return True
    try:
        next_attempt = datetime.fromisoformat(next_attempt_at)
    except ValueError:
        return True
    return next_attempt <= now


class LocalPresignUploadSessionFactory:
    def __init__(self, *, base_url: str, bucket: str, signing_secret: str = "dev-only-secret") -> None:
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self.signing_secret = signing_secret.encode("utf-8")

    def create_session(self, *, tenant_id: str, job_id: str, filename: str) -> UploadSession:
        object_key = f"tenant/{tenant_id}/{job_id}/{filename}"
        expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=15)
        token = self._sign(object_key, int(expires_at.timestamp()))
        query = urlencode({"expires": int(expires_at.timestamp()), "signature": token})
        presigned_url = f"{self.base_url}/{self.bucket}/{object_key}?{query}"
        return UploadSession(
            session_id=f"up_{hashlib.sha1(object_key.encode('utf-8')).hexdigest()[:12]}",
            object_key=object_key,
            presigned_url=presigned_url,
            expires_at=expires_at.isoformat(),
        )

    def _sign(self, object_key: str, expires: int) -> str:
        msg = f"{object_key}:{expires}".encode("utf-8")
        return hmac.new(self.signing_secret, msg=msg, digestmod=hashlib.sha256).hexdigest()


class JsonlAuditLog:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> None:
        enriched = dict(event)
        enriched.setdefault("ts", datetime.now(tz=timezone.utc).isoformat())
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(enriched, ensure_ascii=False, sort_keys=True) + "\n")

    def list_for_tenant(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return [event for event in self.list_all(limit=limit * 5) if event.get("tenant_id") == tenant_id][:limit]

    def list_all(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if len(events) >= limit:
                    break
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    events.append(payload)
        return events


class LocalObjectStorageCatalog:
    def __init__(self) -> None:
        self._objects: dict[str, str] = {}

    def register_object(self, *, object_key: str, checksum_sha256: str) -> None:
        self._objects[object_key] = checksum_sha256

    def exists_with_checksum(self, object_key: str, checksum_sha256: str) -> bool:
        return self._objects.get(object_key) == checksum_sha256

    def delete_prefix(self, *, tenant_id: str, object_prefix: str) -> bool:
        del tenant_id
        keys = [key for key in self._objects if key.startswith(object_prefix)]
        for key in keys:
            self._objects.pop(key, None)
        return True


class LenientObjectStorageCatalog(LocalObjectStorageCatalog):
    def exists_with_checksum(self, object_key: str, checksum_sha256: str) -> bool:
        if super().exists_with_checksum(object_key, checksum_sha256):
            return True
        if not object_key.startswith("tenant/"):
            return False
        if len(checksum_sha256) != 64:
            return False
        return all(ch in "0123456789abcdefABCDEF" for ch in checksum_sha256)


class SQLiteJobCheckpointStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_checkpoints (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    stage_offset INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, job_id)
                )
                """
            )

    def upsert(
        self,
        *,
        tenant_id: str,
        job_id: str,
        stage: str,
        stage_offset: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        safe_payload = payload if isinstance(payload, dict) else {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO job_checkpoints (
                    tenant_id, job_id, stage, stage_offset, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, job_id)
                DO UPDATE SET
                    stage = excluded.stage,
                    stage_offset = excluded.stage_offset,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    tenant_id,
                    job_id,
                    stage,
                    max(0, int(stage_offset)),
                    json.dumps(safe_payload, sort_keys=True),
                    datetime.now(tz=timezone.utc).isoformat(),
                ),
            )

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT stage, stage_offset, payload_json, updated_at
                FROM job_checkpoints
                WHERE tenant_id = ? AND job_id = ?
                """,
                (tenant_id, job_id),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "stage": str(row["stage"] or ""),
            "stage_offset": max(0, int(row["stage_offset"] or 0)),
            "payload": payload,
            "updated_at": row["updated_at"],
        }

    def delete(self, tenant_id: str, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM job_checkpoints WHERE tenant_id = ? AND job_id = ?",
                (tenant_id, job_id),
            )


class SQLiteWorkerArtifactStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_artifacts (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, job_id)
                )
                """
            )

    def put_transcript(self, *, tenant_id: str, job_id: str, artifact: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO worker_artifacts (tenant_id, job_id, payload_json)
                VALUES (?, ?, ?)
                """,
                (tenant_id, job_id, json.dumps(artifact, sort_keys=True)),
            )

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM worker_artifacts WHERE tenant_id = ? AND job_id = ?",
                (tenant_id, job_id),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def delete(self, tenant_id: str, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM worker_artifacts WHERE tenant_id = ? AND job_id = ?",
                (tenant_id, job_id),
            )


class SQLiteTranscriptRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_versions (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    segments_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, job_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcript_versions_latest
                ON transcript_versions (tenant_id, job_id, version DESC)
                """
            )

    def get_current(self, tenant_id: str, job_id: str) -> TranscriptResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version, segments_json
                FROM transcript_versions
                WHERE tenant_id = ? AND job_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (tenant_id, job_id),
            ).fetchone()
            if row is not None:
                return TranscriptResponse(
                    job_id=job_id,
                    version=int(row["version"]),
                    segments=_safe_json_segments(row["segments_json"]),
                )

            artifact = _load_worker_artifact(conn, tenant_id=tenant_id, job_id=job_id)
            if artifact is None:
                return None
            segments = _segments_from_worker_artifact(artifact)
            conn.execute(
                """
                INSERT OR IGNORE INTO transcript_versions (tenant_id, job_id, version, segments_json)
                VALUES (?, ?, 1, ?)
                """,
                (tenant_id, job_id, json.dumps(segments, sort_keys=True)),
            )
            return TranscriptResponse(job_id=job_id, version=1, segments=segments)

    def save_new_version(
        self,
        *,
        tenant_id: str,
        job_id: str,
        expected_base_version: int,
        segments: list[dict[str, Any]],
    ) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version
                FROM transcript_versions
                WHERE tenant_id = ? AND job_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (tenant_id, job_id),
            ).fetchone()

            current_version: int
            if row is None:
                artifact = _load_worker_artifact(conn, tenant_id=tenant_id, job_id=job_id)
                if artifact is None:
                    raise TranscriptValidationError("transcript.not_found", "Transcript wurde nicht gefunden.")
                initial_segments = _segments_from_worker_artifact(artifact)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO transcript_versions (tenant_id, job_id, version, segments_json)
                    VALUES (?, ?, 1, ?)
                    """,
                    (tenant_id, job_id, json.dumps(initial_segments, sort_keys=True)),
                )
                current_version = 1
            else:
                current_version = int(row["version"])

            if current_version != int(expected_base_version):
                raise TranscriptConflictError()

            new_version = current_version + 1
            conn.execute(
                """
                INSERT INTO transcript_versions (tenant_id, job_id, version, segments_json)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, job_id, new_version, json.dumps(segments, sort_keys=True)),
            )
            return new_version

    def delete(self, tenant_id: str, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM transcript_versions WHERE tenant_id = ? AND job_id = ?",
                (tenant_id, job_id),
            )


def _response_to_dict(response: CreateJobResponse) -> dict[str, Any]:
    return {
        "job_id": response.job_id,
        "tenant_id": response.tenant_id,
        "status": response.status,
        "upload": {
            "session_id": response.upload.session_id,
            "object_key": response.upload.object_key,
            "presigned_url": response.upload.presigned_url,
            "expires_at": response.upload.expires_at,
        },
    }


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError("Adapter erwartet dict oder dataclass payload.")


def _load_worker_artifact(conn: sqlite3.Connection, *, tenant_id: str, job_id: str) -> dict[str, Any] | None:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'worker_artifacts'"
    ).fetchone()
    if table_exists is None:
        return None
    row = conn.execute(
        "SELECT payload_json FROM worker_artifacts WHERE tenant_id = ? AND job_id = ?",
        (tenant_id, job_id),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _segments_from_worker_artifact(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    transcript = artifact.get("transcript", {})
    diarization = artifact.get("diarization", {})
    transcript_segments = transcript.get("segments", []) if isinstance(transcript, dict) else []
    diarization_segments = diarization.get("segments", []) if isinstance(diarization, dict) else []

    segments: list[dict[str, Any]] = []
    if isinstance(transcript_segments, list):
        for idx, segment in enumerate(transcript_segments):
            if not isinstance(segment, dict):
                continue
            diarized = diarization_segments[idx] if idx < len(diarization_segments) else {}
            speaker = (
                str(diarized.get("speaker"))
                if isinstance(diarized, dict) and diarized.get("speaker")
                else "UNKNOWN"
            )
            segments.append(
                {
                    "start": float(segment.get("start", 0.0)),
                    "end": float(segment.get("end", 0.0)),
                    "speaker": speaker,
                    "text": str(segment.get("text", "")),
                }
            )

    if segments:
        return segments

    text = ""
    if isinstance(transcript, dict):
        text = str(transcript.get("text", ""))
    return [{"start": 0.0, "end": 0.0, "speaker": "UNKNOWN", "text": text}]


def _safe_json_segments(raw: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
