"""Shared base for read-only JSON vendor APIs: rate limit, retries, typed errors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self

import httpx

from ingest.retry import http_request
from ingest.yahoo.rate_limit import TokenBucket


class VendorError(Exception):
    """Base error for a JSON vendor adapter."""


class VendorHttpError(VendorError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class VendorParseError(VendorError):
    pass


class JsonApiClient:
    """GET-only JSON client. Subclasses set `base_url` and the error types they raise.

    Transport errors and 5xx retry (`ingest.retry.http_get`); 429 fails fast.
    """

    base_url: str = ""
    name: str = "vendor"
    http_error: type[VendorHttpError] = VendorHttpError
    parse_error: type[VendorParseError] = VendorParseError

    def __init__(
        self,
        *,
        rate: float = 2.0,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._bucket = TokenBucket(rate=rate, burst=2)
        self._owns_client = client is None
        self._http = client or httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "MarketAgent/0.1"},
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post_json(self, path: str, body: Mapping[str, Any]) -> Any:
        """POST for query-style read APIs (filters in the body); never a write."""
        return self._request("POST", path, json=dict(body))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        try:
            response = http_request(
                self._http, self._bucket, method, f"{self.base_url}{path}", params=params, json=json
            )
        except httpx.HTTPError as exc:
            raise self.http_error(
                f"{self.name} {path}: request failed ({exc.__class__.__name__})"
            ) from exc
        if response.status_code == 429:
            raise self.http_error(f"{self.name} rate limited", status_code=429)
        if response.status_code >= 400:
            raise self.http_error(
                f"{self.name} {path}: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise self.parse_error(f"{self.name} {path}: response is not JSON") from exc
