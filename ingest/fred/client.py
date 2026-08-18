from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from ingest.fred.errors import FredError, FredHttpError, FredParseError
from ingest.fred.parse import observations_from_payload
from ingest.retry import http_get
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import MacroPoint

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredClient:
    """Official FRED observations endpoint. Do not scrape or wrap a third-party SDK."""

    def __init__(
        self,
        api_key: str,
        *,
        rate: float = 2.0,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise FredError("FRED_API_KEY is missing")
        self._api_key = key
        self._bucket = TokenBucket(rate=rate, burst=5)
        self._owns_client = client is None
        self._http = client or httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "MarketAgent/0.1"},
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> FredClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_observations(
        self,
        series_id: str,
        *,
        observation_start: date | None = None,
    ) -> list[MacroPoint]:
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "asc",
            "units": "lin",
            "limit": 100_000,
        }
        if observation_start is not None:
            params["observation_start"] = observation_start.isoformat()
        try:
            response = http_get(self._http, self._bucket, FRED_OBSERVATIONS_URL, params=params)
        except httpx.HTTPError as exc:
            raise FredHttpError(f"{series_id}: request failed ({exc.__class__.__name__})") from exc
        if response.status_code == 429:
            raise FredHttpError(f"{series_id}: FRED rate limited", status_code=429)
        if response.status_code >= 400:
            raise FredHttpError(
                f"{series_id}: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FredParseError(f"{series_id}: response is not JSON") from exc
        if not isinstance(payload, dict):
            raise FredParseError(f"{series_id}: unexpected JSON payload")
        return observations_from_payload(series_id, payload)
