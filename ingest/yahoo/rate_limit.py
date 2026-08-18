from __future__ import annotations

import threading
import time


class TokenBucket:
    """Process-wide limiter. Yahoo is reliable around 2 requests/second."""

    def __init__(self, *, rate: float = 2.0, burst: float = 5.0) -> None:
        if rate <= 0 or burst < 1:
            raise ValueError("rate must be > 0 and burst >= 1")
        self._rate = rate
        self._capacity = burst
        self._tokens = burst
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            wait = self._wait_locked()
        if wait > 0:
            time.sleep(wait)
            with self._lock:
                self._wait_locked()

    def _wait_locked(self) -> float:
        now = time.monotonic()
        elapsed = now - self._updated
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._updated = now
        if self._tokens >= 1:
            self._tokens -= 1
            return 0.0
        return (1.0 - self._tokens) / self._rate
