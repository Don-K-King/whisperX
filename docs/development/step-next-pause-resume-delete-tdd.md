# Step Next: Pause/Resume/Delete + Progress (TDD)

## Scope
This step delivers an operable job lifecycle for long-running processing jobs:
- `POST /api/v1/jobs/{id}/pause`
- `POST /api/v1/jobs/{id}/resume`
- `DELETE /api/v1/jobs/{id}`
- deterministic progress milestones in API + frontend
- dashboard/detail refresh with polling and 429 backoff

## Status Model
- `queued -> paused` via `pause`
- `processing -> pause_requested` via `pause`
- `pause_requested -> paused` via cooperative worker checks
- `paused -> queued` via `resume`
- `failed_retryable -> queued` via `resume`
- retry limit in worker: `failed_retryable -> failed_terminal` (retry exhausted)
- `completed|failed_terminal|paused|canceled -> deleted` via `delete`

Delete conflict:
- active jobs (`processing|pause_requested|queued`) return `409 job.delete.active_conflict`

## Progress Semantics
Milestone percentages:
- `queued = 5`
- `processing-start = 20`
- `asr-finished = 60`
- `diarization-finished = 90`
- `completed = 100`

Fallback mapping is now centralized and shared across backend/frontend.

## Implementation Summary
Backend:
- Added lifecycle service: `evodox.jobs.lifecycle_service`
- Added centralized progress mapping: `evodox.jobs.progress`
- Extended API adapter with pause/resume/delete endpoints
- Extended SQLite repository/outbox for soft delete and pending-event pruning
- Worker pipeline now updates milestone progress and supports cooperative pausing
- Worker runner now handles retryable vs terminal worker results and retry exhaustion

Frontend:
- Added status-based lifecycle actions in job detail (`Pause`, `Resume`, `Delete`)
- Added polling with `5s` base interval and backoff to `30s` on `429`
- Added upload progress feedback through presigned upload flow
- Added timeline + progress percentage rendering in dashboard/detail

## TDD Sequence Executed
1. Red: API contract tests (pause/resume/delete + conflict behavior)
2. Red: worker pipeline tests (progress milestones + `pause_requested`)
3. Red: worker retry-limit tests (retry -> terminal)
4. Red: frontend tests (progress mapping, actions, backoff, upload progress callback)
5. Green: implementation updates across API, worker, infra, frontend

## Validation
Executed:
- `node --test frontend/tests/*.test.js`
- `docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim python -m unittest discover -s tests -p "test_*.py"`
- `docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "pip install -q fastapi starlette pydantic httpx && python -m unittest tests.test_fastapi_http_adapter_integration tests.test_local_runtime_smoke"`

Result:
- green (all executed tests passed)

## Remaining Work After This Step
- true mid-job checkpointing for pause/resume (current model is stop and restart processing)
- richer progress events beyond milestones (stage timings or ETA)
- explicit cancel endpoint if required by product workflow
- full docker smoke flow including UI-driven pause/resume/delete checks
