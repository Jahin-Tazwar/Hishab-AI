"""Per-tenant token-bucket rate limiter for ingestion LLM calls.

In-process only (single instance is fine for MVP). When we horizontally
scale, swap for a Redis-backed counter.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from uuid import UUID


class RateLimitExceeded(Exception):
    pass


class TokenBucketRegistry:
    """Sliding window over the last 60s and 86400s per tenant."""

    def __init__(self, *, per_min: int, per_day: int) -> None:
        self._per_min = per_min
        self._per_day = per_day
        self._calls: dict[UUID, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def acquire(self, tenant_id: UUID) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._calls[tenant_id]
            # Drop entries older than 1 day
            while q and q[0] < now - 86400:
                q.popleft()
            in_min = sum(1 for t in q if t >= now - 60)
            if in_min >= self._per_min:
                raise RateLimitExceeded(
                    f"tenant {tenant_id}: {in_min}/{self._per_min} in last 60s"
                )
            if len(q) >= self._per_day:
                raise RateLimitExceeded(
                    f"tenant {tenant_id}: {len(q)}/{self._per_day} in last 24h"
                )
            q.append(now)
