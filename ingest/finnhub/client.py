from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from ingest.finnhub.errors import FinnhubError, FinnhubHttpError, FinnhubParseError
from ingest.finnhub.parse import (
    COMPANY_CATEGORY,
    WIRE_CATEGORY,
    events_from_earnings,
    headlines_from_news,
)
from ingest.retry import http_get
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import CalendarEvent, NewsHeadline

FINNHUB_EARNINGS_URL = "https://finnhub.io/api/v1/calendar/earnings"
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"
FINNHUB_COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"


class FinnhubClient:
    """Official Finnhub REST: earnings calendar, market and company news.

    Do not scrape article pages or add finnhub-python.
    """

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
        """Unfiltered calendars are capped (~1500 rows), so known symbols are asked one by one."""
        window = {"from": start.isoformat(), "to": end.isoformat()}
        if not symbols:
            return events_from_earnings(self._calendar(window))
        out: list[CalendarEvent] = []
        for symbol in sorted(item.upper() for item in symbols):
            payload = self._calendar({**window, "symbol": symbol})
            out.extend(events_from_earnings(payload, allowed={symbol}))
        return out

    def fetch_market_news(self, *, category: str = "general") -> list[NewsHeadline]:
        """Finnhub market news (Reuters / CNBC / Bloomberg wire), newest ~100 rows."""
        payload = self._get(FINNHUB_NEWS_URL, {"category": category}, "news")
        return headlines_from_news(payload, category=WIRE_CATEGORY, query=category)

    def fetch_company_news(
        self, symbol: str, *, start: date, end: date, cap: int
    ) -> list[NewsHeadline]:
        """Company news for one symbol; keeps the newest `cap` rows that carry a real summary."""
        params = {"symbol": symbol.upper(), "from": start.isoformat(), "to": end.isoformat()}
        payload = self._get(FINNHUB_COMPANY_NEWS_URL, params, f"company-news {symbol}")
        rows = headlines_from_news(payload, category=COMPANY_CATEGORY, query=symbol.upper())
        rows.sort(key=lambda item: item.published_at, reverse=True)
        return [item for item in rows if item.summary][:cap]

    def _calendar(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = self._get(FINNHUB_EARNINGS_URL, params, "earnings")
        if not isinstance(payload, dict):
            raise FinnhubParseError("earnings: unexpected JSON payload")
        return payload

    def _get(self, url: str, params: dict[str, Any], label: str) -> Any:
        try:
            response = http_get(self._http, self._bucket, url, params=params)
        except httpx.HTTPError as exc:
            raise FinnhubHttpError(
                f"{label}: request failed ({exc.__class__.__name__})"
            ) from exc
        if response.status_code == 429:
            raise FinnhubHttpError(f"{label}: Finnhub rate limited", status_code=429)
        if response.status_code == 401:
            raise FinnhubHttpError(f"{label}: unauthorized", status_code=401)
        if response.status_code >= 400:
            raise FinnhubHttpError(
                f"{label}: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise FinnhubParseError(f"{label}: response is not JSON") from exc
