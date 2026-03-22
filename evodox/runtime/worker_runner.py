from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import signal
import threading
import time
from typing import Any, Callable

from evodox.jobs.infrastructure import (
    JsonlAuditLog,
    SQLiteJobRepository,
    SQLiteOutbox,
    SQLiteWorkerArtifactStore,
)
from evodox.jobs.worker_pipeline_service import WorkerPipeline, WorkerProcessInput

LOGGER = logging.getLogger("evodox.runtime.worker_runner")


class WorkerRuntimeConfigError(ValueError):
    pass


@dataclass(frozen=True)
class WorkerRuntimeSettings:
    db_path: Path
    poll_interval_seconds: int = 2
    batch_size: int = 25
    mode: str = "stub"
    audit_log_path: Path = Path("/runtime/audit/worker-audit.jsonl")
    max_ticks: int | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "WorkerRuntimeSettings":
        source = env if env is not None else os.environ
        db_path = source.get("WORKER_DB_PATH", "/runtime/jobs.db").strip()
        if not db_path:
            raise WorkerRuntimeConfigError("WORKER_DB_PATH ist erforderlich.")

        poll_interval = _parse_positive_int(source.get("WORKER_POLL_INTERVAL_SECONDS", "2"), "WORKER_POLL_INTERVAL_SECONDS")
        batch_size = _parse_positive_int(source.get("WORKER_BATCH_SIZE", "25"), "WORKER_BATCH_SIZE")
        mode = source.get("WORKER_MODE", "stub").strip().lower()
        if mode != "stub":
            raise WorkerRuntimeConfigError("WORKER_MODE muss aktuell 'stub' sein.")

        audit_log_path = Path(source.get("WORKER_AUDIT_LOG_PATH", "/runtime/audit/worker-audit.jsonl").strip())
        max_ticks = _parse_optional_positive_int(source.get("WORKER_MAX_TICKS", ""), "WORKER_MAX_TICKS")

        return cls(
            db_path=Path(db_path),
            poll_interval_seconds=poll_interval,
            batch_size=batch_size,
            mode=mode,
            audit_log_path=audit_log_path,
            max_ticks=max_ticks,
        )


@dataclass(frozen=True)
class WorkerTickResult:
    processed: int
    failed: int


class WorkerRuntime:
    def __init__(self, *, settings: WorkerRuntimeSettings) -> None:
        self.settings = settings
        self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        self.job_repository = SQLiteJobRepository(self.settings.db_path)
        self.outbox = SQLiteOutbox(self.settings.db_path)
        self.audit_log = JsonlAuditLog(self.settings.audit_log_path)
        self.artifact_store = SQLiteWorkerArtifactStore(self.settings.db_path)
        self.pipeline = WorkerPipeline(
            job_store=self.job_repository,
            artifact_store=self.artifact_store,
            audit_log=self.audit_log,
            asr_engine=_stub_asr_engine,
            align_engine=_stub_align_engine,
            diarize_engine=_stub_diarize_engine,
        )

    def run_once(self) -> WorkerTickResult:
        processed = 0
        failed = 0
        now = datetime.now(tz=timezone.utc)

        for event in self.outbox.list_pending(limit=self.settings.batch_size):
            if not _is_due(event.get("next_attempt_at"), now=now):
                continue
            payload = event.get("payload", {})
            if event.get("event_type") != "job.queued":
                self.outbox.mark_dlq(
                    event["event_id"],
                    reason="worker.unsupported_event",
                    error_code="worker.unsupported_event",
                    error_class="terminal",
                )
                failed += 1
                continue

            tenant_id = str(payload.get("tenant_id") or event.get("tenant_id") or "").strip()
            job_id = str(payload.get("job_id") or event.get("job_id") or "").strip()
            object_key = str(payload.get("object_key") or "").strip()
            checksum_sha256 = str(payload.get("checksum_sha256") or "").strip()
            upload_session_id = str(payload.get("upload_session_id") or "").strip()
            if not tenant_id or not job_id:
                self.outbox.mark_dlq(
                    event["event_id"],
                    reason="worker.invalid_payload",
                    error_code="worker.invalid_payload",
                    error_class="terminal",
                )
                failed += 1
                continue

            try:
                if object_key:
                    self.job_repository.mark_queued(
                        tenant_id,
                        job_id,
                        object_key=object_key,
                        checksum_sha256=checksum_sha256,
                        upload_session_id=upload_session_id,
                    )
                self.pipeline.process(WorkerProcessInput(tenant_id=tenant_id, job_id=job_id))
                self.outbox.mark_published(event["event_id"])
                processed += 1
            except Exception as exc:
                self.outbox.mark_retry(
                    event["event_id"],
                    error_code=f"worker.{type(exc).__name__}",
                    next_attempt_at=now + timedelta(seconds=self.settings.poll_interval_seconds),
                )
                failed += 1

        return WorkerTickResult(processed=processed, failed=failed)


@dataclass
class WorkerRunner:
    runtime: WorkerRuntime
    settings: WorkerRuntimeSettings
    stop_event: threading.Event
    sleep_fn: Callable[[int], None]
    logger: logging.Logger

    def run_forever(self) -> int:
        tick_count = 0
        while not self.stop_event.is_set():
            result = self.runtime.run_once()
            self.logger.info(
                "worker.runner.tick_completed",
                extra={"event": {"processed": result.processed, "failed": result.failed}},
            )
            tick_count += 1
            if self.settings.max_ticks is not None and tick_count >= self.settings.max_ticks:
                break
            if self.stop_event.is_set():
                break
            self.sleep_fn(self.settings.poll_interval_seconds)

        self.logger.info("worker.runner.stopped")
        return 0


def create_worker_runner(
    *,
    env: dict[str, str] | None = None,
    stop_event: threading.Event | None = None,
    sleep_fn: Callable[[int], None] = time.sleep,
    signal_module: Any = signal,
    logger: logging.Logger = LOGGER,
) -> WorkerRunner:
    settings = WorkerRuntimeSettings.from_env(env)
    runtime = WorkerRuntime(settings=settings)
    shutdown_event = stop_event or threading.Event()
    _install_signal_handlers(shutdown_event, signal_module=signal_module, logger=logger)
    logger.info(
        "worker.runner.started",
        extra={
            "event": {
                "db_path": str(settings.db_path),
                "mode": settings.mode,
                "batch_size": settings.batch_size,
                "poll_interval_seconds": settings.poll_interval_seconds,
            }
        },
    )
    return WorkerRunner(
        runtime=runtime,
        settings=settings,
        stop_event=shutdown_event,
        sleep_fn=sleep_fn,
        logger=logger,
    )


def run_worker_runner(
    *,
    env: dict[str, str] | None = None,
    stop_event: threading.Event | None = None,
    sleep_fn: Callable[[int], None] = time.sleep,
    signal_module: Any = signal,
    logger: logging.Logger = LOGGER,
) -> int:
    try:
        runner = create_worker_runner(
            env=env,
            stop_event=stop_event,
            sleep_fn=sleep_fn,
            signal_module=signal_module,
            logger=logger,
        )
    except WorkerRuntimeConfigError as exc:
        logger.error("worker.runner.config_error", extra={"event": {"error": str(exc)}})
        return 2
    return runner.run_forever()


def main() -> int:
    _configure_logging()
    return run_worker_runner()


def _stub_asr_engine(object_key: str) -> dict[str, Any]:
    filename = object_key.rsplit("/", 1)[-1] if "/" in object_key else object_key
    text = f"Stub transcript for {filename}"
    return {
        "text": text,
        "language": "de",
        "segments": [{"start": 0.0, "end": 1.0, "text": text}],
    }


def _stub_align_engine(transcript: dict[str, Any]) -> dict[str, Any]:
    return {
        "aligned": True,
        "segments": list(transcript.get("segments", [])),
    }


def _stub_diarize_engine(alignment: dict[str, Any]) -> dict[str, Any]:
    diarized_segments = []
    for segment in alignment.get("segments", []):
        diarized_segments.append(
            {
                "speaker": "SPEAKER_00",
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
            }
        )
    return {"segments": diarized_segments}


def _is_due(next_attempt_at: str | None, *, now: datetime) -> bool:
    if not next_attempt_at:
        return True
    try:
        parsed = datetime.fromisoformat(next_attempt_at)
    except ValueError:
        return True
    return parsed <= now


def _install_signal_handlers(stop_event: threading.Event, *, signal_module: Any, logger: logging.Logger) -> None:
    def _handle_shutdown(signum: int, _frame: Any) -> None:
        logger.info("worker.runner.shutdown_requested", extra={"event": {"signal": signum}})
        stop_event.set()

    signal_module.signal(signal_module.SIGTERM, _handle_shutdown)
    signal_module.signal(signal_module.SIGINT, _handle_shutdown)


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("WORKER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _parse_positive_int(raw: str, key: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise WorkerRuntimeConfigError(f"{key} muss eine Zahl sein.") from exc
    if value <= 0:
        raise WorkerRuntimeConfigError(f"{key} muss > 0 sein.")
    return value


def _parse_optional_positive_int(raw: str, key: str) -> int | None:
    value = raw.strip()
    if not value:
        return None
    return _parse_positive_int(value, key)


if __name__ == "__main__":
    raise SystemExit(main())
