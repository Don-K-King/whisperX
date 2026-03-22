from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
from typing import Any

from .progress import derive_progress


ALLOWED_SOURCE_STATUSES = frozenset({"queued", "failed_retryable"})
_STAGE_ORDER = {
    "downloaded": 1,
    "asr_started": 2,
    "asr_done": 3,
    "diarization_done": 4,
}


class WorkerPipelineError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


class RetryableWorkerError(WorkerPipelineError):
    pass


class TerminalWorkerError(WorkerPipelineError):
    pass


class WorkerInterruptionRequested(Exception):
    def __init__(self, requested_status: str):
        self.requested_status = str(requested_status or "")
        super().__init__(self.requested_status)


@dataclass(frozen=True)
class WorkerProcessInput:
    tenant_id: str
    job_id: str


@dataclass(frozen=True)
class WorkerProcessResult:
    tenant_id: str
    job_id: str
    status: str
    error_code: str | None = None


class InMemoryJobStateStore:
    def __init__(self, initial: dict[tuple[str, str], dict[str, Any]] | None = None) -> None:
        self._jobs = dict(initial or {})

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        item = self._jobs.get((tenant_id, job_id))
        return None if item is None else dict(item)

    def set_status(self, tenant_id: str, job_id: str, status: str, *, progress: int | None = None) -> None:
        key = (tenant_id, job_id)
        if key not in self._jobs:
            raise KeyError("job not found")
        self._jobs[key]["status"] = status
        if progress is not None:
            self._jobs[key]["progress"] = int(progress)


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    def put_transcript(self, *, tenant_id: str, job_id: str, artifact: dict[str, Any]) -> None:
        self._items[(tenant_id, job_id)] = dict(artifact)

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        item = self._items.get((tenant_id, job_id))
        return None if item is None else dict(item)


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    def upsert(
        self,
        *,
        tenant_id: str,
        job_id: str,
        stage: str,
        stage_offset: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._items[(tenant_id, job_id)] = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "stage": str(stage),
            "stage_offset": max(0, int(stage_offset)),
            "payload": dict(payload or {}),
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        item = self._items.get((tenant_id, job_id))
        return None if item is None else dict(item)

    def delete(self, tenant_id: str, job_id: str) -> None:
        self._items.pop((tenant_id, job_id), None)


class InMemoryWorkerAuditLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


class WorkerPipeline:
    def __init__(
        self,
        *,
        job_store: Any,
        artifact_store: Any,
        checkpoint_store: Any | None,
        audit_log: Any,
        asr_engine: Any,
        align_engine: Any,
        diarize_engine: Any,
        asr_checkpoint_interval: int = 1,
    ) -> None:
        self.job_store = job_store
        self.artifact_store = artifact_store
        self.checkpoint_store = checkpoint_store
        self.audit_log = audit_log
        self.asr_engine = asr_engine
        self.align_engine = align_engine
        self.diarize_engine = diarize_engine
        self.asr_checkpoint_interval = max(1, int(asr_checkpoint_interval))

    def process(self, request: WorkerProcessInput) -> WorkerProcessResult:
        job = self.job_store.get(request.tenant_id, request.job_id)
        if job is None:
            raise KeyError("job.not_found")
        if job.get("status") not in ALLOWED_SOURCE_STATUSES:
            raise ValueError("job.invalid_state")

        self.job_store.set_status(request.tenant_id, request.job_id, "processing", progress=20)
        self.audit_log.append(
            {
                "action": "job.worker.start",
                "tenant_id": request.tenant_id,
                "job_id": request.job_id,
                "ts": datetime.now(tz=timezone.utc).isoformat(),
            }
        )

        try:
            interrupt = self._interrupt_if_requested(request)
            if interrupt is not None:
                return interrupt

            object_key = str(job.get("object_key", ""))
            expected_prefix = f"tenant/{request.tenant_id}/{request.job_id}/"
            if not object_key.startswith(expected_prefix):
                raise TerminalWorkerError("job.object_key_scope_violation")

            checkpoint = self._load_checkpoint(request)
            stage = str((checkpoint or {}).get("stage") or "")

            if _stage_rank(stage) < _stage_rank("downloaded"):
                self._write_checkpoint(
                    request=request,
                    stage="downloaded",
                    stage_offset=0,
                    payload={"object_key": object_key},
                )

            interrupt = self._interrupt_if_requested(
                request,
                stage="downloaded",
                stage_offset=0,
                payload={"object_key": object_key},
            )
            if interrupt is not None:
                return interrupt

            if stage == "diarization_done":
                artifact = self._artifact_from_checkpoint(checkpoint)
            else:
                transcript, interrupt = self._run_asr_stage(request=request, object_key=object_key)
                if interrupt is not None:
                    return interrupt
                self.job_store.set_status(request.tenant_id, request.job_id, "processing", progress=60)

                interrupt = self._interrupt_if_requested(
                    request,
                    stage="asr_done",
                    stage_offset=len(transcript.get("segments", [])),
                    payload={"transcript": transcript},
                )
                if interrupt is not None:
                    return interrupt

                aligned = self.align_engine(transcript)
                interrupt = self._interrupt_if_requested(
                    request,
                    stage="asr_done",
                    stage_offset=len(transcript.get("segments", [])),
                    payload={"transcript": transcript},
                )
                if interrupt is not None:
                    return interrupt

                diarized = self.diarize_engine(aligned)
                self.job_store.set_status(request.tenant_id, request.job_id, "processing", progress=90)
                artifact = {
                    "tenant_id": request.tenant_id,
                    "job_id": request.job_id,
                    "transcript": transcript,
                    "alignment": aligned,
                    "diarization": diarized,
                }
                self._write_checkpoint(
                    request=request,
                    stage="diarization_done",
                    stage_offset=0,
                    payload=artifact,
                )

            interrupt = self._interrupt_if_requested(
                request,
                stage="diarization_done",
                stage_offset=0,
                payload=artifact,
            )
            if interrupt is not None:
                return interrupt

            self.artifact_store.put_transcript(
                tenant_id=request.tenant_id,
                job_id=request.job_id,
                artifact=artifact,
            )
            self.job_store.set_status(request.tenant_id, request.job_id, "completed", progress=100)
            self.audit_log.append(
                {
                    "action": "job.worker.completed",
                    "tenant_id": request.tenant_id,
                    "job_id": request.job_id,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
            return WorkerProcessResult(tenant_id=request.tenant_id, job_id=request.job_id, status="completed")
        except RetryableWorkerError as exc:
            self.job_store.set_status(request.tenant_id, request.job_id, "failed_retryable")
            self.audit_log.append(
                {
                    "action": "job.worker.failed",
                    "tenant_id": request.tenant_id,
                    "job_id": request.job_id,
                    "error_code": exc.error_code,
                    "retryable": True,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
            return WorkerProcessResult(
                tenant_id=request.tenant_id,
                job_id=request.job_id,
                status="failed_retryable",
                error_code=exc.error_code,
            )
        except TerminalWorkerError as exc:
            self.job_store.set_status(request.tenant_id, request.job_id, "failed_terminal")
            self.audit_log.append(
                {
                    "action": "job.worker.failed",
                    "tenant_id": request.tenant_id,
                    "job_id": request.job_id,
                    "error_code": exc.error_code,
                    "retryable": False,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
            return WorkerProcessResult(
                tenant_id=request.tenant_id,
                job_id=request.job_id,
                status="failed_terminal",
                error_code=exc.error_code,
            )

    def _run_asr_stage(
        self,
        *,
        request: WorkerProcessInput,
        object_key: str,
    ) -> tuple[dict[str, Any], WorkerProcessResult | None]:
        checkpoint = self._load_checkpoint(request)
        stage = str((checkpoint or {}).get("stage") or "")
        payload = dict((checkpoint or {}).get("payload") or {})
        checkpoint_transcript = _normalize_transcript(payload.get("transcript"))

        if _stage_rank(stage) >= _stage_rank("asr_done") and (
            checkpoint_transcript.get("segments") or checkpoint_transcript.get("text")
        ):
            return checkpoint_transcript, None

        stage_offset = 0
        merged_segments: list[dict[str, Any]] = []
        prior_text = ""
        language = "und"
        if stage == "asr_started":
            stage_offset = max(0, int((checkpoint or {}).get("stage_offset") or 0))
            merged_segments = [dict(item) for item in checkpoint_transcript.get("segments", []) if isinstance(item, dict)]
            prior_text = str(checkpoint_transcript.get("text") or "")
            language = str(checkpoint_transcript.get("language") or "und")

        try:
            asr_payload = _normalize_transcript(
                self._call_asr_engine(
                    object_key,
                    stage_offset=stage_offset,
                    interrupt_check=lambda: self._poll_interrupt_signal(request),
                )
            )
        except WorkerInterruptionRequested:
            interrupt = self._interrupt_if_requested(
                request,
                stage="asr_started",
                stage_offset=stage_offset,
                payload={"transcript": {"text": prior_text, "language": language, "segments": list(merged_segments)}},
            )
            if interrupt is not None:
                return {}, interrupt
            return {}, WorkerProcessResult(tenant_id=request.tenant_id, job_id=request.job_id, status="failed_terminal", error_code="worker.interrupted")
        language = str(asr_payload.get("language") or language or "und")
        incoming_segments = [dict(item) for item in asr_payload.get("segments", []) if isinstance(item, dict)]
        # Fallback fuer Engines ohne stage_offset-Unterstuetzung: bereits checkpointed Prefix nicht doppelt verarbeiten.
        incoming_segments = _drop_checkpoint_prefix(
            incoming_segments=incoming_segments,
            checkpoint_segments=merged_segments,
            stage_offset=stage_offset,
        )
        if not incoming_segments and not merged_segments:
            incoming_segments = [
                {
                    "start": 0.0,
                    "end": 0.0,
                    "text": str(asr_payload.get("text") or ""),
                    "speaker": "UNKNOWN",
                }
            ]

        for index, segment in enumerate(incoming_segments, start=1):
            merged_segments.append(_normalize_segment(segment))
            absolute_offset = len(merged_segments)
            should_checkpoint = index % self.asr_checkpoint_interval == 0 or index == len(incoming_segments)
            if should_checkpoint:
                checkpoint_payload = {
                    "transcript": {
                        "text": _merge_text(prior_text, asr_payload.get("text", ""), fallback=_segments_to_text(merged_segments)),
                        "language": language,
                        "segments": list(merged_segments),
                    }
                }
                self._write_checkpoint(
                    request=request,
                    stage="asr_started",
                    stage_offset=absolute_offset,
                    payload=checkpoint_payload,
                )
                interrupt = self._interrupt_if_requested(
                    request,
                    stage="asr_started",
                    stage_offset=absolute_offset,
                    payload=checkpoint_payload,
                )
                if interrupt is not None:
                    return {}, interrupt

        transcript = {
            "text": _merge_text(prior_text, asr_payload.get("text", ""), fallback=_segments_to_text(merged_segments)),
            "language": language,
            "segments": list(merged_segments),
        }
        self._write_checkpoint(
            request=request,
            stage="asr_done",
            stage_offset=len(merged_segments),
            payload={"transcript": transcript},
        )
        return transcript, None

    def _interrupt_if_requested(
        self,
        request: WorkerProcessInput,
        *,
        stage: str | None = None,
        stage_offset: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> WorkerProcessResult | None:
        current = self.job_store.get(request.tenant_id, request.job_id)
        if current is None:
            return None
        status = str(current.get("status") or "")

        if status == "cancel_requested":
            if stage:
                self._write_checkpoint(request=request, stage=stage, stage_offset=stage_offset, payload=payload)
            self.job_store.set_status(request.tenant_id, request.job_id, "canceled", progress=100)
            self.audit_log.append(
                {
                    "action": "job.worker.canceled",
                    "tenant_id": request.tenant_id,
                    "job_id": request.job_id,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
            return WorkerProcessResult(tenant_id=request.tenant_id, job_id=request.job_id, status="canceled")

        if status == "pause_requested":
            if stage:
                self._write_checkpoint(request=request, stage=stage, stage_offset=stage_offset, payload=payload)
            progress = derive_progress(status=status, raw_progress=current.get("progress"))
            self.job_store.set_status(request.tenant_id, request.job_id, "paused", progress=progress)
            self.audit_log.append(
                {
                    "action": "job.worker.paused",
                    "tenant_id": request.tenant_id,
                    "job_id": request.job_id,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
            return WorkerProcessResult(tenant_id=request.tenant_id, job_id=request.job_id, status="paused")

        if status == "deleted":
            if stage:
                self._write_checkpoint(request=request, stage=stage, stage_offset=stage_offset, payload=payload)
            self.audit_log.append(
                {
                    "action": "job.worker.deleted",
                    "tenant_id": request.tenant_id,
                    "job_id": request.job_id,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
            return WorkerProcessResult(tenant_id=request.tenant_id, job_id=request.job_id, status="deleted")

        return None

    def _poll_interrupt_signal(self, request: WorkerProcessInput) -> str | None:
        current = self.job_store.get(request.tenant_id, request.job_id)
        if current is None:
            return None
        status = str(current.get("status") or "")
        if status in {"pause_requested", "cancel_requested", "deleted"}:
            return status
        return None

    def _load_checkpoint(self, request: WorkerProcessInput) -> dict[str, Any] | None:
        getter = getattr(self.checkpoint_store, "get", None)
        if not callable(getter):
            return None
        value = getter(request.tenant_id, request.job_id)
        if value is None or not isinstance(value, dict):
            return None
        return value

    def _write_checkpoint(
        self,
        *,
        request: WorkerProcessInput,
        stage: str,
        stage_offset: int,
        payload: dict[str, Any] | None,
    ) -> None:
        upsert = getattr(self.checkpoint_store, "upsert", None)
        if callable(upsert):
            upsert(
                tenant_id=request.tenant_id,
                job_id=request.job_id,
                stage=stage,
                stage_offset=max(0, int(stage_offset)),
                payload=payload or {},
            )

    def _artifact_from_checkpoint(self, checkpoint: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict((checkpoint or {}).get("payload") or {})
        transcript = _normalize_transcript(payload.get("transcript"))
        alignment = payload.get("alignment") if isinstance(payload.get("alignment"), dict) else {"segments": transcript.get("segments", [])}
        diarization = payload.get("diarization") if isinstance(payload.get("diarization"), dict) else {"segments": []}
        return {
            "tenant_id": str((checkpoint or {}).get("tenant_id") or ""),
            "job_id": str((checkpoint or {}).get("job_id") or ""),
            "transcript": transcript,
            "alignment": alignment,
            "diarization": diarization,
        }

    def _call_asr_engine(
        self,
        object_key: str,
        *,
        stage_offset: int,
        interrupt_check: Any | None = None,
    ) -> dict[str, Any]:
        supports_offset = False
        supports_interrupt_check = False
        try:
            signature = inspect.signature(self.asr_engine)
            supports_offset = "stage_offset" in signature.parameters
            supports_interrupt_check = "interrupt_check" in signature.parameters
        except (TypeError, ValueError):
            supports_offset = False
            supports_interrupt_check = False

        kwargs: dict[str, Any] = {}
        if supports_offset:
            kwargs["stage_offset"] = stage_offset
        if supports_interrupt_check and interrupt_check is not None:
            kwargs["interrupt_check"] = interrupt_check
        result = self.asr_engine(object_key, **kwargs) if kwargs else self.asr_engine(object_key)
        if not isinstance(result, dict):
            return {}
        return result


def _normalize_transcript(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    segments = payload.get("segments", [])
    normalized_segments = [_normalize_segment(item) for item in segments] if isinstance(segments, list) else []
    text = str(payload.get("text") or "")
    language = str(payload.get("language") or "und")
    return {
        "text": text,
        "language": language,
        "segments": normalized_segments,
    }


def _normalize_segment(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    return {
        "start": float(payload.get("start", 0.0)),
        "end": float(payload.get("end", 0.0)),
        "text": str(payload.get("text") or ""),
        "speaker": str(payload.get("speaker") or "UNKNOWN"),
    }


def _merge_text(base: Any, new: Any, *, fallback: str) -> str:
    left = str(base or "").strip()
    right = str(new or "").strip()
    if left and right:
        return f"{left} {right}".strip()
    if right:
        return right
    if left:
        return left
    return str(fallback or "")


def _segments_to_text(segments: list[dict[str, Any]]) -> str:
    return " ".join(str(item.get("text") or "").strip() for item in segments if str(item.get("text") or "").strip())


def _stage_rank(stage: str) -> int:
    return _STAGE_ORDER.get(str(stage or ""), 0)


def _drop_checkpoint_prefix(
    *,
    incoming_segments: list[dict[str, Any]],
    checkpoint_segments: list[dict[str, Any]],
    stage_offset: int,
) -> list[dict[str, Any]]:
    normalized = [_normalize_segment(item) for item in incoming_segments]
    if stage_offset <= 0 or not checkpoint_segments or not normalized:
        return normalized
    prefix_len = min(stage_offset, len(checkpoint_segments), len(normalized))
    if prefix_len <= 0:
        return normalized
    checkpoint_prefix = [_normalize_segment(item) for item in checkpoint_segments[:prefix_len]]
    incoming_prefix = normalized[:prefix_len]
    if all(
        str(incoming_prefix[index].get("text") or "").strip() == str(checkpoint_prefix[index].get("text") or "").strip()
        for index in range(prefix_len)
    ):
        return normalized[prefix_len:]
    return normalized
