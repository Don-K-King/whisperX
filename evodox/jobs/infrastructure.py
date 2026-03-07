from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlencode

from .complete_upload_service import CompleteUploadIdempotencyRecord, CompleteUploadResponse
from .create_service import CreateJobResponse, IdempotencyRecord, UploadSession


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
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

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
                    event_type TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    queue TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    published_at TEXT
                )
                """
            )

    def append(self, event: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outbox_events (event_type, tenant_id, job_id, queue, payload_json, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (
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
                "event_type": row["event_type"],
                "tenant_id": row["tenant_id"],
                "job_id": row["job_id"],
                "queue": row["queue"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def mark_published(self, event_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE outbox_events SET status = 'published', published_at = ? WHERE event_id = ?",
                (datetime.now(tz=timezone.utc).isoformat(), event_id),
            )


class OutboxQueueDispatcher:
    def __init__(self, *, outbox: SQLiteOutbox, queue_publisher: Any) -> None:
        self.outbox = outbox
        self.queue_publisher = queue_publisher

    def dispatch_pending(self, *, limit: int = 100) -> int:
        published = 0
        for event in self.outbox.list_pending(limit=limit):
            self.queue_publisher.publish(event["queue"], event["payload"])
            self.outbox.mark_published(event["event_id"])
            published += 1
        return published


class InMemoryQueuePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def publish(self, queue_name: str, payload: dict[str, Any]) -> None:
        self.messages.append((queue_name, dict(payload)))


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
