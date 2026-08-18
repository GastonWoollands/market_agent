from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import httpx

ATTEMPTS = 3


class RateLimiter(Protocol):
    def acquire(self) -> None: ...


def retryable_status(status: int | None) -> bool:
    """Retry timeouts (None) and 5xx. Never retry 429 — northstar fail-fast."""
    if status is None:
        return True
    if status == 429:
        return False
    return status >= 500


def retry_call[T](
    fn: Callable[[], T],
    *,
    attempts: int = ATTEMPTS,
    retryable: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    last: Exception | None = None
    for index in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if index >= attempts - 1 or not retryable(exc):
                raise
            sleep(min(2**index, 4))
    assert last is not None
    raise last


def http_get(
    http: httpx.Client,
    bucket: RateLimiter,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET with token bucket. Retries transport errors and 5xx. Returns 429 to the caller."""
    last_response: httpx.Response | None = None
    last_error: Exception | None = None
    for index in range(attempts):
        bucket.acquire()
        try:
            response = http.get(url, params=params)
        except httpx.HTTPError as exc:
            last_error = exc
            if index >= attempts - 1:
                raise
            sleep(min(2**index, 4))
            continue
        last_response = response
        if response.status_code == 429:
            return response
        if retryable_status(response.status_code) and index < attempts - 1:
            sleep(min(2**index, 4))
            continue
        return response
    if last_response is not None:
        return last_response
    assert last_error is not None
    raise last_error
