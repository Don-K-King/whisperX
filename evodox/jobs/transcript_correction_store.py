from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SQLiteTranscriptCorrectionStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_correction_sessions (
                    tenant_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    base_version INTEGER NOT NULL,
                    autosave_enabled INTEGER NOT NULL DEFAULT 0,
                    speaker_labels_json TEXT NOT NULL DEFAULT '{}',
                    review_status TEXT NOT NULL DEFAULT 'in_review',
                    is_final INTEGER NOT NULL DEFAULT 0,
                    history_index INTEGER NOT NULL DEFAULT 0,
                    history_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, session_id)
                )
                """
            )
            session_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(transcript_correction_sessions)").fetchall()
            }
            if "autosave_enabled" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN autosave_enabled INTEGER NOT NULL DEFAULT 0"
                )
            if "speaker_labels_json" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN speaker_labels_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "review_status" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN review_status TEXT NOT NULL DEFAULT 'in_review'"
                )
            if "is_final" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN is_final INTEGER NOT NULL DEFAULT 0"
                )
            if "history_index" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN history_index INTEGER NOT NULL DEFAULT 0"
                )
            if "history_json" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN history_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "updated_at" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            if "created_at" not in session_columns:
                conn.execute(
                    "ALTER TABLE transcript_correction_sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_status (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'in_review',
                    is_final INTEGER NOT NULL DEFAULT 0,
                    final_set_by TEXT,
                    final_set_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (tenant_id, job_id)
                )
                """
            )
            status_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(transcript_status)").fetchall()
            }
            if "final_set_by" not in status_columns:
                conn.execute("ALTER TABLE transcript_status ADD COLUMN final_set_by TEXT")
            if "final_set_at" not in status_columns:
                conn.execute("ALTER TABLE transcript_status ADD COLUMN final_set_at TEXT")
            if "updated_at" not in status_columns:
                conn.execute("ALTER TABLE transcript_status ADD COLUMN updated_at TEXT")

    def create_session(self, *, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload["session_id"])
        job_id = str(payload["job_id"])
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        updated_at = str(payload.get("updated_at") or now_iso)
        created_at = str(payload.get("created_at") or now_iso)
        expires_at = str(payload.get("expires_at") or updated_at)
        with self._connect() as conn:
            session_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(transcript_correction_sessions)").fetchall()
            }
            pk_columns = _primary_key_columns(conn, "transcript_correction_sessions")
            if "job_id" in pk_columns and "session_id" not in pk_columns:
                existing_session_id = _find_session_id_by_job(conn, tenant_id=tenant_id, job_id=job_id)
                if existing_session_id:
                    return self.get_session(tenant_id=tenant_id, session_id=existing_session_id) or dict(payload)
            try:
                if "expires_at" in session_columns:
                    conn.execute(
                        """
                        INSERT INTO transcript_correction_sessions (
                            tenant_id, session_id, job_id, actor_id, base_version, autosave_enabled,
                            speaker_labels_json, review_status, is_final, history_index, history_json,
                            expires_at, updated_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tenant_id,
                            session_id,
                            job_id,
                            str(payload["actor_id"]),
                            int(payload["base_version"]),
                            1 if bool(payload.get("autosave_enabled", False)) else 0,
                            json.dumps(payload.get("speaker_labels", {}), sort_keys=True),
                            str(payload.get("review_status", "in_review")),
                            1 if bool(payload.get("is_final", False)) else 0,
                            int(payload.get("history_index", 0)),
                            json.dumps(payload.get("history", []), sort_keys=True),
                            expires_at,
                            updated_at,
                            created_at,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO transcript_correction_sessions (
                            tenant_id, session_id, job_id, actor_id, base_version, autosave_enabled,
                            speaker_labels_json, review_status, is_final, history_index, history_json, updated_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tenant_id,
                            session_id,
                            job_id,
                            str(payload["actor_id"]),
                            int(payload["base_version"]),
                            1 if bool(payload.get("autosave_enabled", False)) else 0,
                            json.dumps(payload.get("speaker_labels", {}), sort_keys=True),
                            str(payload.get("review_status", "in_review")),
                            1 if bool(payload.get("is_final", False)) else 0,
                            int(payload.get("history_index", 0)),
                            json.dumps(payload.get("history", []), sort_keys=True),
                            updated_at,
                            created_at,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                if "UNIQUE constraint failed" not in str(exc):
                    raise
                existing_session_id = _find_session_id_by_job(conn, tenant_id=tenant_id, job_id=job_id)
                if not existing_session_id:
                    raise
                return self.get_session(tenant_id=tenant_id, session_id=existing_session_id) or dict(payload)
        return self.get_session(tenant_id=tenant_id, session_id=session_id) or dict(payload)

    def get_session(self, *, tenant_id: str, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT job_id, actor_id, base_version, autosave_enabled, speaker_labels_json,
                       review_status, is_final, history_index, history_json, updated_at, created_at
                FROM transcript_correction_sessions
                WHERE tenant_id = ? AND session_id = ?
                """,
                (tenant_id, session_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "session_id": session_id,
            "job_id": str(row["job_id"]),
            "actor_id": str(row["actor_id"]),
            "base_version": int(row["base_version"]),
            "autosave_enabled": bool(int(row["autosave_enabled"])),
            "speaker_labels": _safe_json_object(row["speaker_labels_json"]),
            "review_status": str(row["review_status"] or "in_review"),
            "is_final": bool(int(row["is_final"])),
            "history_index": int(row["history_index"]),
            "history": _safe_json_list(row["history_json"]),
            "updated_at": row["updated_at"],
            "created_at": row["created_at"],
        }

    def update_session(self, *, tenant_id: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE transcript_correction_sessions
                SET job_id = ?,
                    actor_id = ?,
                    base_version = ?,
                    autosave_enabled = ?,
                    speaker_labels_json = ?,
                    review_status = ?,
                    is_final = ?,
                    history_index = ?,
                    history_json = ?,
                    updated_at = ?
                WHERE tenant_id = ? AND session_id = ?
                """,
                (
                    str(payload["job_id"]),
                    str(payload["actor_id"]),
                    int(payload["base_version"]),
                    1 if bool(payload.get("autosave_enabled", False)) else 0,
                    json.dumps(payload.get("speaker_labels", {}), sort_keys=True),
                    str(payload.get("review_status", "in_review")),
                    1 if bool(payload.get("is_final", False)) else 0,
                    int(payload.get("history_index", 0)),
                    json.dumps(payload.get("history", []), sort_keys=True),
                    str(payload.get("updated_at") or datetime.now(tz=timezone.utc).isoformat()),
                    tenant_id,
                    session_id,
                ),
            )
        if updated.rowcount == 0:
            raise KeyError("session not found")
        return self.get_session(tenant_id=tenant_id, session_id=session_id) or dict(payload)

    def delete_session(self, *, tenant_id: str, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM transcript_correction_sessions WHERE tenant_id = ? AND session_id = ?",
                (tenant_id, session_id),
            )

    def get_status(self, *, tenant_id: str, job_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT review_status, is_final, final_set_by, final_set_at, updated_at
                FROM transcript_status
                WHERE tenant_id = ? AND job_id = ?
                """,
                (tenant_id, job_id),
            ).fetchone()
        if row is None:
            return {
                "review_status": "in_review",
                "is_final": False,
                "final_set_by": None,
                "final_set_at": None,
                "updated_at": None,
            }
        return {
            "review_status": str(row["review_status"] or "in_review"),
            "is_final": bool(int(row["is_final"])),
            "final_set_by": row["final_set_by"],
            "final_set_at": row["final_set_at"],
            "updated_at": row["updated_at"],
        }

    def set_status(
        self,
        *,
        tenant_id: str,
        job_id: str,
        review_status: str | None,
        is_final: bool | None,
        actor_id: str,
    ) -> dict[str, Any]:
        current = self.get_status(tenant_id=tenant_id, job_id=job_id)
        now = datetime.now(tz=timezone.utc).isoformat()
        next_status = {
            "review_status": current["review_status"] if review_status is None else review_status,
            "is_final": current["is_final"] if is_final is None else bool(is_final),
            "final_set_by": current.get("final_set_by"),
            "final_set_at": current.get("final_set_at"),
            "updated_at": now,
        }
        if is_final is True:
            next_status["final_set_by"] = actor_id
            next_status["final_set_at"] = now
        if is_final is False:
            next_status["final_set_by"] = None
            next_status["final_set_at"] = None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO transcript_status (
                    tenant_id, job_id, review_status, is_final, final_set_by, final_set_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, job_id)
                DO UPDATE SET
                    review_status = excluded.review_status,
                    is_final = excluded.is_final,
                    final_set_by = excluded.final_set_by,
                    final_set_at = excluded.final_set_at,
                    updated_at = excluded.updated_at
                """,
                (
                    tenant_id,
                    job_id,
                    str(next_status["review_status"]),
                    1 if bool(next_status["is_final"]) else 0,
                    next_status.get("final_set_by"),
                    next_status.get("final_set_at"),
                    next_status.get("updated_at"),
                ),
            )
        return dict(next_status)


def _safe_json_object(raw: Any) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return dict(data)


def _safe_json_list(raw: Any) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _find_session_id_by_job(conn: sqlite3.Connection, *, tenant_id: str, job_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT session_id
        FROM transcript_correction_sessions
        WHERE tenant_id = ? AND job_id = ?
        LIMIT 1
        """,
        (tenant_id, job_id),
    ).fetchone()
    if row is None:
        return None
    session_id = row["session_id"]
    if session_id is None:
        return None
    return str(session_id)


def _primary_key_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    keyed = [(int(row["pk"]), str(row["name"])) for row in rows if int(row["pk"]) > 0]
    keyed.sort(key=lambda item: item[0])
    return [name for _, name in keyed]
