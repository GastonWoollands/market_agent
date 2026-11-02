from __future__ import annotations

from datetime import date

import httpx

from ingest.cboe.errors import CboeHttpError, CboeParseError
from ingest.cboe.parse import stats_from_payload
from ingest.retry import http_get
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import CboeProductStat

DAILY_URL = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{day}_daily_options"


class CboeClient:
    """Cboe daily market-statistics JSON: the one sanctioned unofficial endpoint (Northstar §6).

    The file behind the public statistics page. Never parse cboe.com HTML.
    """

    def __init__(
        self,
        *,
        rate: float = 1.0,
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

    def __enter__(self) -> CboeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_day(self, day: date) -> list[CboeProductStat] | None:
        """The day's stats, or None when Cboe has no file for it (403/404: not published)."""
        url = DAILY_URL.format(day=day.isoformat())
        try:
            response = http_get(self._http, self._bucket, url)
        except httpx.HTTPError as exc:
            raise CboeHttpError(f"{day}: request failed ({exc.__class__.__name__})") from exc
        if response.status_code in (403, 404):
            return None
        if response.status_code >= 400:
            raise CboeHttpError(
                f"{day}: HTTP {response.status_code}", status_code=response.status_code
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CboeParseError(f"{day}: response is not JSON") from exc
        return stats_from_payload(day, payload)
