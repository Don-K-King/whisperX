from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from evodox.jobs.infrastructure import (
    JsonlAuditLog,
    SQLiteJobRepository,
    SQLiteOutbox,
    SQLiteWorkerArtifactStore,
)
from evodox.jobs.worker_pipeline_service import (
    RetryableWorkerError,
    TerminalWorkerError,
    WorkerPipeline,
    WorkerProcessInput,
)

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
    object_storage_base_url: str = "http://object-storage:9000"
    object_storage_bucket: str = "uploads"
    whisperx_model: str = "tiny"
    whisperx_device: str = "cpu"
    whisperx_compute_type: str = "int8"
    whisperx_batch_size: int = 4
    whisperx_model_dir: Path = Path("/runtime/models")
    enable_diarization: bool = True
    diarization_model: str = "pyannote/speaker-diarization"
    hf_token: str | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    whisperx_vad_method: str = "silero"
    media_temp_dir: Path = Path("/tmp/evodox-worker")
    whisperx_timeout_seconds: int = 7200
    worker_max_retries: int = 3

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "WorkerRuntimeSettings":
        source = env if env is not None else os.environ
        db_path = source.get("WORKER_DB_PATH", "/runtime/jobs.db").strip()
        if not db_path:
            raise WorkerRuntimeConfigError("WORKER_DB_PATH ist erforderlich.")

        poll_interval = _parse_positive_int(source.get("WORKER_POLL_INTERVAL_SECONDS", "2"), "WORKER_POLL_INTERVAL_SECONDS")
        batch_size = _parse_positive_int(source.get("WORKER_BATCH_SIZE", "25"), "WORKER_BATCH_SIZE")
        mode = source.get("WORKER_MODE", "stub").strip().lower()
        if mode not in {"stub", "whisperx"}:
            raise WorkerRuntimeConfigError("WORKER_MODE muss 'stub' oder 'whisperx' sein.")

        audit_log_path = Path(source.get("WORKER_AUDIT_LOG_PATH", "/runtime/audit/worker-audit.jsonl").strip())
        max_ticks = _parse_optional_positive_int(source.get("WORKER_MAX_TICKS", ""), "WORKER_MAX_TICKS")
        object_storage_base_url = source.get("WORKER_OBJECT_STORAGE_BASE_URL", "http://object-storage:9000").strip()
        object_storage_bucket = source.get("WORKER_OBJECT_STORAGE_BUCKET", "uploads").strip()
        whisperx_model = source.get("WORKER_WHISPERX_MODEL", "tiny").strip()
        whisperx_device = source.get("WORKER_WHISPERX_DEVICE", "cpu").strip().lower()
        whisperx_compute_type = source.get("WORKER_WHISPERX_COMPUTE_TYPE", "int8").strip().lower()
        whisperx_batch_size = _parse_positive_int(source.get("WORKER_WHISPERX_BATCH_SIZE", "4"), "WORKER_WHISPERX_BATCH_SIZE")
        whisperx_model_dir = Path(source.get("WORKER_WHISPERX_MODEL_DIR", "/runtime/models").strip())
        enable_diarization = _parse_bool(source.get("WORKER_ENABLE_DIARIZATION", "true"))
        diarization_model = source.get(
            "WORKER_WHISPERX_DIARIZATION_MODEL",
            "pyannote/speaker-diarization",
        ).strip()
        hf_token = (
            source.get("WORKER_HF_TOKEN")
            or source.get("HF_TOKEN")
            or source.get("HUGGINGFACE_HUB_TOKEN")
            or ""
        ).strip()
        min_speakers = _parse_optional_positive_int(source.get("WORKER_WHISPERX_MIN_SPEAKERS", ""), "WORKER_WHISPERX_MIN_SPEAKERS")
        max_speakers = _parse_optional_positive_int(source.get("WORKER_WHISPERX_MAX_SPEAKERS", ""), "WORKER_WHISPERX_MAX_SPEAKERS")
        whisperx_vad_method = source.get("WORKER_WHISPERX_VAD_METHOD", "silero").strip().lower()
        media_temp_dir = Path(source.get("WORKER_MEDIA_TEMP_DIR", "/tmp/evodox-worker").strip())
        whisperx_timeout_seconds = _parse_positive_int(
            source.get("WORKER_WHISPERX_TIMEOUT_SECONDS", "7200"),
            "WORKER_WHISPERX_TIMEOUT_SECONDS",
        )
        worker_max_retries = _parse_non_negative_int(source.get("WORKER_MAX_RETRIES", "3"), "WORKER_MAX_RETRIES")

        if mode == "whisperx":
            if not object_storage_base_url:
                raise WorkerRuntimeConfigError("WORKER_OBJECT_STORAGE_BASE_URL ist erforderlich.")
            if not object_storage_bucket:
                raise WorkerRuntimeConfigError("WORKER_OBJECT_STORAGE_BUCKET ist erforderlich.")
            if enable_diarization and not hf_token:
                raise WorkerRuntimeConfigError(
                    "HF_TOKEN oder HUGGINGFACE_HUB_TOKEN ist erforderlich, wenn WORKER_ENABLE_DIARIZATION=true."
                )
            if min_speakers is not None and max_speakers is not None and max_speakers < min_speakers:
                raise WorkerRuntimeConfigError("WORKER_WHISPERX_MAX_SPEAKERS muss >= WORKER_WHISPERX_MIN_SPEAKERS sein.")
            if whisperx_vad_method not in {"silero", "pyannote"}:
                raise WorkerRuntimeConfigError("WORKER_WHISPERX_VAD_METHOD muss 'silero' oder 'pyannote' sein.")

        return cls(
            db_path=Path(db_path),
            poll_interval_seconds=poll_interval,
            batch_size=batch_size,
            mode=mode,
            audit_log_path=audit_log_path,
            max_ticks=max_ticks,
            object_storage_base_url=object_storage_base_url,
            object_storage_bucket=object_storage_bucket,
            whisperx_model=whisperx_model or "tiny",
            whisperx_device=whisperx_device or "cpu",
            whisperx_compute_type=whisperx_compute_type or "int8",
            whisperx_batch_size=whisperx_batch_size,
            whisperx_model_dir=whisperx_model_dir,
            enable_diarization=enable_diarization,
            diarization_model=diarization_model or "pyannote/speaker-diarization",
            hf_token=hf_token or None,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            whisperx_vad_method=whisperx_vad_method or "silero",
            media_temp_dir=media_temp_dir,
            whisperx_timeout_seconds=whisperx_timeout_seconds,
            worker_max_retries=worker_max_retries,
        )


@dataclass(frozen=True)
class WorkerTickResult:
    processed: int
    failed: int


class WorkerRuntime:
    def __init__(
        self,
        *,
        settings: WorkerRuntimeSettings,
        media_fetcher: Callable[[str], Path] | None = None,
        whisperx_runner: Callable[[Path, WorkerRuntimeSettings], dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings
        self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.media_temp_dir.mkdir(parents=True, exist_ok=True)
        self.settings.whisperx_model_dir.mkdir(parents=True, exist_ok=True)

        self.job_repository = SQLiteJobRepository(self.settings.db_path)
        self.outbox = SQLiteOutbox(self.settings.db_path)
        self.audit_log = JsonlAuditLog(self.settings.audit_log_path)
        self.artifact_store = SQLiteWorkerArtifactStore(self.settings.db_path)
        asr_engine, align_engine, diarize_engine = _build_processing_engines(
            settings=self.settings,
            media_fetcher=media_fetcher,
            whisperx_runner=whisperx_runner,
        )
        self.pipeline = WorkerPipeline(
            job_store=self.job_repository,
            artifact_store=self.artifact_store,
            audit_log=self.audit_log,
            asr_engine=asr_engine,
            align_engine=align_engine,
            diarize_engine=diarize_engine,
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
            job_row = self.job_repository.get(tenant_id, job_id)
            if job_row is None:
                self.outbox.mark_dlq(
                    event["event_id"],
                    reason="worker.job_not_found",
                    error_code="job.not_found",
                    error_class="terminal",
                )
                failed += 1
                continue
            current_status = str(job_row.get("status") or "")
            if current_status in {"paused", "pause_requested", "deleted", "canceled"}:
                self.outbox.mark_published(event["event_id"])
                processed += 1
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
                result = self.pipeline.process(WorkerProcessInput(tenant_id=tenant_id, job_id=job_id))
                if result.status in {"completed", "paused"}:
                    self.outbox.mark_published(event["event_id"])
                    processed += 1
                    continue
                if result.status == "failed_retryable":
                    if event.get("retry_count", 0) + 1 > self.settings.worker_max_retries:
                        self.outbox.mark_dlq(
                            event["event_id"],
                            reason="retry_exhausted",
                            error_code=result.error_code or "worker.retry_exhausted",
                            error_class="retryable",
                        )
                        try:
                            self.job_repository.set_status(tenant_id, job_id, "failed_terminal")
                        except KeyError:
                            pass
                        self.audit_log.append(
                            {
                                "action": "job.worker.retry_exhausted",
                                "tenant_id": tenant_id,
                                "job_id": job_id,
                                "error_code": result.error_code or "worker.retry_exhausted",
                                "ts": datetime.now(tz=timezone.utc).isoformat(),
                            }
                        )
                        processed += 1
                    else:
                        self.outbox.mark_retry(
                            event["event_id"],
                            error_code=result.error_code or "worker.retryable_error",
                            next_attempt_at=now + timedelta(seconds=self.settings.poll_interval_seconds),
                        )
                    failed += 1
                    continue
                if result.status == "failed_terminal":
                    self.outbox.mark_dlq(
                        event["event_id"],
                        reason="terminal_worker_error",
                        error_code=result.error_code or "worker.failed_terminal",
                        error_class="terminal",
                    )
                    processed += 1
                    failed += 1
                    continue

                self.outbox.mark_dlq(
                    event["event_id"],
                    reason="worker.invalid_result",
                    error_code="worker.invalid_result",
                    error_class="terminal",
                )
                failed += 1
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
                "diarization_enabled": settings.enable_diarization,
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
        "__diarization": transcript.get("__diarization"),
    }


def _stub_diarize_engine(alignment: dict[str, Any]) -> dict[str, Any]:
    precomputed = alignment.get("__diarization")
    if isinstance(precomputed, dict):
        return precomputed
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


def _build_processing_engines(
    *,
    settings: WorkerRuntimeSettings,
    media_fetcher: Callable[[str], Path] | None,
    whisperx_runner: Callable[[Path, WorkerRuntimeSettings], dict[str, Any]] | None,
) -> tuple[Callable[[str], dict[str, Any]], Callable[[dict[str, Any]], dict[str, Any]], Callable[[dict[str, Any]], dict[str, Any]]]:
    if settings.mode == "stub":
        return _stub_asr_engine, _stub_align_engine, _stub_diarize_engine

    fetcher = media_fetcher or _build_media_fetcher(settings)
    runner = whisperx_runner or _run_whisperx_subprocess
    asr_engine = _create_whisperx_asr_engine(settings=settings, media_fetcher=fetcher, whisperx_runner=runner)
    return asr_engine, _whisperx_align_engine, _whisperx_diarize_engine


def _create_whisperx_asr_engine(
    *,
    settings: WorkerRuntimeSettings,
    media_fetcher: Callable[[str], Path],
    whisperx_runner: Callable[[Path, WorkerRuntimeSettings], dict[str, Any]],
) -> Callable[[str], dict[str, Any]]:
    def _engine(object_key: str) -> dict[str, Any]:
        media_path = media_fetcher(object_key)
        try:
            payload = whisperx_runner(media_path, settings)
            transcript = _normalize_transcript(payload.get("transcript"))
            diarization = _normalize_diarization(payload.get("diarization"), transcript_segments=transcript.get("segments", []))
            transcript["__diarization"] = diarization
            return transcript
        finally:
            _safe_unlink(media_path)

    return _engine


def _whisperx_align_engine(transcript: dict[str, Any]) -> dict[str, Any]:
    return {
        "aligned": True,
        "segments": list(transcript.get("segments", [])),
        "__diarization": transcript.get("__diarization"),
    }


def _whisperx_diarize_engine(alignment: dict[str, Any]) -> dict[str, Any]:
    return _normalize_diarization(
        alignment.get("__diarization"),
        transcript_segments=alignment.get("segments", []),
    )


def _build_media_fetcher(settings: WorkerRuntimeSettings) -> Callable[[str], Path]:
    base_url = settings.object_storage_base_url.rstrip("/")
    bucket = settings.object_storage_bucket.strip().strip("/")
    if not base_url or not bucket:
        raise WorkerRuntimeConfigError("WORKER_OBJECT_STORAGE_BASE_URL und WORKER_OBJECT_STORAGE_BUCKET sind erforderlich.")

    def _fetch(object_key: str) -> Path:
        safe_key = _sanitize_object_key(object_key)
        if safe_key is None:
            raise TerminalWorkerError("worker.invalid_object_key")

        encoded_key = urlparse.quote(safe_key, safe="/")
        object_url = f"{base_url}/{bucket}/{encoded_key}"
        suffix = Path(safe_key).suffix or ".bin"
        with tempfile.NamedTemporaryFile(prefix="evodox-media-", suffix=suffix, dir=settings.media_temp_dir, delete=False) as handle:
            temp_path = Path(handle.name)
            try:
                with urlrequest.urlopen(object_url, timeout=120) as response:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
            except urlerror.HTTPError as exc:
                _safe_unlink(temp_path)
                if exc.code == 404:
                    raise TerminalWorkerError("worker.object_not_found") from exc
                raise RetryableWorkerError("worker.media_download_failed") from exc
            except urlerror.URLError as exc:
                _safe_unlink(temp_path)
                raise RetryableWorkerError("worker.media_download_failed") from exc
            except Exception as exc:
                _safe_unlink(temp_path)
                raise RetryableWorkerError("worker.media_download_failed") from exc
        return temp_path

    return _fetch


def _run_whisperx_subprocess(media_path: Path, settings: WorkerRuntimeSettings) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="evodox-whisperx-out-") as output_dir_raw:
        output_dir = Path(output_dir_raw)
        completed = _run_whisperx_command(
            command=_build_whisperx_command(
                media_path=media_path,
                output_dir=output_dir,
                settings=settings,
                include_diarization=settings.enable_diarization,
            ),
            settings=settings,
        )
        if completed.returncode != 0 and settings.enable_diarization:
            LOGGER.warning(
                "worker.whisperx.diarization_fallback",
                extra={
                    "event": {
                        "returncode": completed.returncode,
                        "stderr_tail": completed.stderr[-2000:],
                    }
                },
            )
            for file in output_dir.glob("*"):
                _safe_unlink(file)
            completed = _run_whisperx_command(
                command=_build_whisperx_command(
                    media_path=media_path,
                    output_dir=output_dir,
                    settings=settings,
                    include_diarization=False,
                ),
                settings=settings,
            )

        if completed.returncode != 0:
            LOGGER.error(
                "worker.whisperx.command_failed",
                extra={
                    "event": {
                        "returncode": completed.returncode,
                        "stderr_tail": completed.stderr[-2000:],
                    }
                },
            )
            raise TerminalWorkerError("worker.transcription_failed")

        output_json = _resolve_whisperx_output(output_dir=output_dir, media_path=media_path)
        payload = json.loads(output_json.read_text(encoding="utf-8"))
        transcript = _normalize_transcript(payload)
        diarization = _normalize_diarization(payload, transcript_segments=transcript.get("segments", []))
        return {"transcript": transcript, "diarization": diarization}


def _run_whisperx_command(*, command: list[str], settings: WorkerRuntimeSettings) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=settings.whisperx_timeout_seconds,
    )


def _build_whisperx_command(
    *,
    media_path: Path,
    output_dir: Path,
    settings: WorkerRuntimeSettings,
    include_diarization: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "whisperx",
        str(media_path),
        "--model",
        settings.whisperx_model,
        "--device",
        settings.whisperx_device,
        "--batch_size",
        str(settings.whisperx_batch_size),
        "--compute_type",
        settings.whisperx_compute_type,
        "--output_format",
        "json",
        "--output_dir",
        str(output_dir),
        "--model_dir",
        str(settings.whisperx_model_dir),
        "--verbose",
        "False",
        "--print_progress",
        "False",
        "--vad_method",
        settings.whisperx_vad_method,
    ]

    if include_diarization:
        command.extend(
            [
                "--diarize",
                "--diarize_model",
                settings.diarization_model,
            ]
        )
        if settings.hf_token:
            command.extend(["--hf_token", settings.hf_token])
        if settings.min_speakers is not None:
            command.extend(["--min_speakers", str(settings.min_speakers)])
        if settings.max_speakers is not None:
            command.extend(["--max_speakers", str(settings.max_speakers)])
    return command


def _resolve_whisperx_output(*, output_dir: Path, media_path: Path) -> Path:
    direct = output_dir / f"{media_path.stem}.json"
    if direct.exists():
        return direct
    matches = sorted(output_dir.glob("*.json"))
    if matches:
        return matches[0]
    raise TerminalWorkerError("worker.transcription_output_missing")


def _normalize_transcript(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    segments = _normalize_transcript_segments(payload.get("segments"))
    text = str(payload.get("text") or "")
    language = str(payload.get("language") or "und")
    if not segments and text:
        segments = [{"start": 0.0, "end": 0.0, "text": text}]
    return {
        "text": text,
        "language": language,
        "segments": segments,
    }


def _normalize_transcript_segments(raw_segments: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_segments, list):
        return []
    segments: list[dict[str, Any]] = []
    for raw in raw_segments:
        if not isinstance(raw, dict):
            continue
        segments.append(
            {
                "start": float(raw.get("start", 0.0)),
                "end": float(raw.get("end", 0.0)),
                "text": str(raw.get("text", "")),
                "speaker": str(raw.get("speaker", "UNKNOWN")),
            }
        )
    return segments


def _normalize_diarization(raw: Any, *, transcript_segments: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("segments"), list):
        normalized: list[dict[str, Any]] = []
        for segment in raw.get("segments", []):
            if not isinstance(segment, dict):
                continue
            normalized.append(
                {
                    "speaker": str(segment.get("speaker") or "UNKNOWN"),
                    "start": float(segment.get("start", 0.0)),
                    "end": float(segment.get("end", 0.0)),
                }
            )
        if normalized:
            return {"segments": normalized}
    return {"segments": _segments_to_diarization(transcript_segments)}


def _segments_to_diarization(transcript_segments: Any) -> list[dict[str, Any]]:
    if not isinstance(transcript_segments, list):
        return [{"speaker": "UNKNOWN", "start": 0.0, "end": 0.0}]
    diarization: list[dict[str, Any]] = []
    for segment in transcript_segments:
        if not isinstance(segment, dict):
            continue
        diarization.append(
            {
                "speaker": str(segment.get("speaker") or "UNKNOWN"),
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
            }
        )
    if diarization:
        return diarization
    return [{"speaker": "UNKNOWN", "start": 0.0, "end": 0.0}]


def _sanitize_object_key(raw_key: str) -> str | None:
    key = str(raw_key).strip().replace("\\", "/")
    if not key or not key.startswith("tenant/"):
        return None
    if ".." in key:
        return None
    return key


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


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


def _parse_non_negative_int(raw: str, key: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise WorkerRuntimeConfigError(f"{key} muss eine Zahl sein.") from exc
    if value < 0:
        raise WorkerRuntimeConfigError(f"{key} muss >= 0 sein.")
    return value


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
