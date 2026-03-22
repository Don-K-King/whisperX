from __future__ import annotations

from typing import Any

MILESTONE_PROGRESS = {
    "queued": 5,
    "processing": 20,
    "pause_requested": 20,
    "paused": 20,
    "failed_retryable": 20,
    "failed_terminal": 20,
    "completed": 100,
    "canceled": 100,
    "deleted": 100,
}


def derive_progress(*, status: str, raw_progress: Any) -> int:
    if isinstance(raw_progress, int):
        return max(0, min(100, raw_progress))
    default = MILESTONE_PROGRESS.get(str(status), 0)
    return max(0, min(100, int(default)))
