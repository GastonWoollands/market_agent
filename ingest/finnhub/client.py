from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from ingest.finnhub.errors import FinnhubError, FinnhubHttpError, FinnhubParseError
from ingest.finnhub.parse import events_from_earnings
from ingest.retry import http_get
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import CalendarEvent

FINNHUB_EARNINGS_URL = "https://finnhub.io/api/v1/calendar/earnings"


class FinnhubClient:
    """Official Finnhub earnings calendar. Do not scrape calendars or add finnhub-python."""

    def __init__(
        self,
        api_key: str,
        *,
        rate: float = 1.0,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise FinnhubError("FINNHUB_API_KEY is missing")
        self._api_key = key
        self._bucket = TokenBucket(rate=rate, burst=3)
        self._owns_client = client is None
        self._http = client or httpx.Client(
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "MarketAgent/0.1",
                "X-Finnhub-Token": key,
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> FinnhubClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_earnings(
        self,
        *,
        start: date,
        end: date,
        symbols: set[str] | None = None,
    ) -> list[CalendarEvent]:
        params: dict[str, Any] = {"from": start.isoformat(), "to": end.isoformat()}
        try:
            response = http_get(self._http, self._bucket, FINNHUB_EARNINGS_URL, params=params)
        except httpx.HTTPError as exc:
            raise FinnhubHttpError(
                f"earnings: request failed ({exc.__class__.__name__})"
            ) from exc
        if response.status_code == 429:
            raise FinnhubHttpError("earnings: Finnhub rate limited", status_code=429)
        if response.status_code == 401:
            raise FinnhubHttpError("earnings: unauthorized", status_code=401)
        if response.status_code >= 400:
            raise FinnhubHttpError(
                f"earnings: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FinnhubParseError("earnings: response is not JSON") from exc
        if not isinstance(payload, dict):
            raise FinnhubParseError("earnings: unexpected JSON payload")
        return events_from_earnings(payload, allowed=symbols)
