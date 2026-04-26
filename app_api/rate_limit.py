"""Small in-memory rate limiter with injectable clock."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable


class RateLimiter:
    """Sliding-window per-key rate limiter."""

    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float],
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clock = clock
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = self.clock()
        window_start = now - self.window_seconds
        timestamps = [ts for ts in self._requests[key] if ts > window_start]
        self._requests[key] = timestamps

        if len(timestamps) >= self.max_requests:
            return False

        timestamps.append(now)
        return True
