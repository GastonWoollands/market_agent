from __future__ import annotations

import httpx

from ingest.fed_rss.errors import FedRssHttpError, FedRssParseError
from ingest.fed_rss.parse import docs_from_rss
from ingest.retry import http_get
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import PolicyDoc

FEEDS = {
    "press_monetary": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "speeches": "https://www.federalreserve.gov/feeds/speeches.xml",
    "testimony": "https://www.federalreserve.gov/feeds/testimony.xml",
}


class FedRssClient:
    """Federal Reserve Board RSS. Do not fetch speech HTML."""

    def __init__(
        self,
        *,
        rate: float = 2.0,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._bucket = TokenBucket(rate=rate, burst=5)
        self._owns_client = client is None
        self._http = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
                "User-Agent": "MarketAgent/0.1 (US research terminal; Fed Board RSS)",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> FedRssClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_feed(self, feed: str) -> list[PolicyDoc]:
        url = FEEDS.get(feed)
        if url is None:
            raise FedRssParseError(f"unknown feed {feed}")
        try:
            response = http_get(self._http, self._bucket, url)
        except httpx.HTTPError as exc:
            raise FedRssHttpError(f"{feed}: request failed ({exc.__class__.__name__})") from exc
        if response.status_code == 429:
            raise FedRssHttpError(f"{feed}: RSS rate limited", status_code=429)
        if response.status_code >= 400:
            raise FedRssHttpError(
                f"{feed}: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return docs_from_rss(response.text, feed=feed)
        except FedRssParseError:
            raise
        except Exception as exc:
            raise FedRssParseError(f"{feed}: RSS parse failed") from exc
