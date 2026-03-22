from __future__ import annotations

from collections import Counter, deque
from typing import Any


class TenantFairnessPolicy:
    def __init__(self, *, max_inflight_global: int, max_inflight_per_tenant: int) -> None:
        if max_inflight_global < 1 or max_inflight_per_tenant < 1:
            raise ValueError("limits must be >= 1")
        self.max_inflight_global = max_inflight_global
        self.max_inflight_per_tenant = max_inflight_per_tenant
        self._inflight_total = 0
        self._inflight_per_tenant: Counter[str] = Counter()
        self._queues: dict[str, deque[Any]] = {}
        self._rr: deque[str] = deque()

    def try_start(self, tenant_id: str) -> bool:
        if self._inflight_total >= self.max_inflight_global:
            return False
        if self._inflight_per_tenant[tenant_id] >= self.max_inflight_per_tenant:
            return False
        self._inflight_total += 1
        self._inflight_per_tenant[tenant_id] += 1
        return True

    def finish(self, tenant_id: str) -> None:
        if self._inflight_per_tenant[tenant_id] > 0:
            self._inflight_per_tenant[tenant_id] -= 1
            self._inflight_total = max(0, self._inflight_total - 1)

    def enqueue(self, tenant_id: str, message: Any) -> None:
        if tenant_id not in self._queues:
            self._queues[tenant_id] = deque()
            self._rr.append(tenant_id)
        self._queues[tenant_id].append(message)

    def dequeue_next(self) -> tuple[str, Any]:
        if not self._rr:
            raise IndexError("no queued messages")
        for _ in range(len(self._rr)):
            tenant_id = self._rr[0]
            self._rr.rotate(-1)
            queue = self._queues.get(tenant_id)
            if not queue:
                continue
            msg = queue.popleft()
            if not queue:
                self._queues.pop(tenant_id, None)
                self._rr = deque([t for t in self._rr if t != tenant_id])
            return tenant_id, msg
        raise IndexError("no queued messages")
