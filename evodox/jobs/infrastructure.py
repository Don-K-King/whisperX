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
from .retention_service import RetentionCandidate


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
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "deleted_at" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN deleted_at TEXT")

    def create(self, job: Any) -> None:
        payload = _to_dict(job)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, tenant_id, actor_id, filename, content_type, size_bytes, retention_months, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["job_id"],
                    payload["tenant_id"],
                    payload["actor_id"],
                    payload["filename"],
                    payload["content_type"],
                    int(payload["size_bytes"]),
                    int(payload["retention_months"]),
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

    def set_status(self, tenant_id: str, job_id: str, status: str) -> None:
        with self._connect() as conn:
            updated = conn.execute(
                "UPDATE jobs SET status = ? WHERE tenant_id = ? AND job_id = ?",
                (status, tenant_id, job_id),
            )
        if updated.rowcount == 0:
            raise KeyError("job not found")

    def list_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE tenant_id = ? ORDER BY created_at", (tenant_id,)
            ).fetchall()
        return [dict(row) for row in rows]


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


class LocalObjectStorageCatalog:
    def __init__(self) -> None:
        self._objects: dict[str, str] = {}

    def register_object(self, *, object_key: str, checksum_sha256: str) -> None:
        self._objects[object_key] = checksum_sha256

    def exists_with_checksum(self, object_key: str, checksum_sha256: str) -> bool:
        return self._objects.get(object_key) == checksum_sha256


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
