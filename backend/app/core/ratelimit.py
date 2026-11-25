"""In-memory sliding-window rate limiter.

Good for a single API instance. When the API scales to several instances,
swap the storage for Redis (planned with the background worker in M6).
"""

from collections import deque
from time import monotonic

from fastapi import Request

from app.core.errors import RateLimited


class SlidingWindowLimiter:
    def __init__(self, max_keys: int = 10_000) -> None:
        self._events: dict[str, deque[float]] = {}
        self._max_keys = max_keys

    def hit(self, key: str, *, limit: int, window_seconds: float) -> None:
        now = monotonic()
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if len(events) >= limit:
            retry_after = int(window_seconds - (now - events[0])) + 1
            raise RateLimited(
                "Too many requests. Please slow down.",
                headers={"Retry-After": str(retry_after)},
                retry_after_seconds=retry_after,
            )
        events.append(now)
        if len(self._events) > self._max_keys:
            self._prune(now, window_seconds)

    def _prune(self, now: float, window_seconds: float) -> None:
        stale = [k for k, q in self._events.items() if not q or q[-1] <= now - window_seconds]
        for key in stale:
            del self._events[key]

    def reset(self) -> None:
        self._events.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
