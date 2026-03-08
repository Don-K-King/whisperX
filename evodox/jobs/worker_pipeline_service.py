from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


ALLOWED_SOURCE_STATUSES = frozenset({"queued", "failed_retryable"})


class WorkerPipelineError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


class RetryableWorkerError(WorkerPipelineError):
    pass


class TerminalWorkerError(WorkerPipelineError):
    pass


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

    def set_status(self, tenant_id: str, job_id: str, status: str) -> None:
        key = (tenant_id, job_id)
        if key not in self._jobs:
            raise KeyError("job not found")
        self._jobs[key]["status"] = status


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    def put_transcript(self, *, tenant_id: str, job_id: str, artifact: dict[str, Any]) -> None:
        self._items[(tenant_id, job_id)] = dict(artifact)

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        item = self._items.get((tenant_id, job_id))
        return None if item is None else dict(item)


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
        audit_log: Any,
        asr_engine: Any,
        align_engine: Any,
        diarize_engine: Any,
    ) -> None:
        self.job_store = job_store
        self.artifact_store = artifact_store
        self.audit_log = audit_log
        self.asr_engine = asr_engine
        self.align_engine = align_engine
        self.diarize_engine = diarize_engine

    def process(self, request: WorkerProcessInput) -> WorkerProcessResult:
        job = self.job_store.get(request.tenant_id, request.job_id)
        if job is None:
            raise KeyError("job.not_found")
        if job.get("status") not in ALLOWED_SOURCE_STATUSES:
            raise ValueError("job.invalid_state")

        self.job_store.set_status(request.tenant_id, request.job_id, "processing")
        self.audit_log.append(
            {
                "action": "job.worker.start",
                "tenant_id": request.tenant_id,
                "job_id": request.job_id,
                "ts": datetime.now(tz=timezone.utc).isoformat(),
            }
        )

        try:
            object_key = str(job.get("object_key", ""))
            expected_prefix = f"tenant/{request.tenant_id}/{request.job_id}/"
            if not object_key.startswith(expected_prefix):
                raise TerminalWorkerError("job.object_key_scope_violation")
            transcript = self.asr_engine(object_key)
            aligned = self.align_engine(transcript)
            diarized = self.diarize_engine(aligned)
            artifact = {
                "tenant_id": request.tenant_id,
                "job_id": request.job_id,
                "transcript": transcript,
                "alignment": aligned,
                "diarization": diarized,
            }
            self.artifact_store.put_transcript(
                tenant_id=request.tenant_id,
                job_id=request.job_id,
                artifact=artifact,
            )
            self.job_store.set_status(request.tenant_id, request.job_id, "completed")
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
