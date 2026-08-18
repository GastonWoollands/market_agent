from __future__ import annotations

import httpx

from ingest.news_rss.errors import NewsHttpError, NewsParseError
from ingest.news_rss.parse import headlines_from_rss
from ingest.retry import http_get
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import NewsHeadline

NEWS_RSS_URL = "https://news.google.com/rss/search"


class NewsClient:
    """Google News RSS search. Do not scrape news.google.com HTML or add a news SDK."""

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
                # Google News RSS 403s non-browser UAs; this is still the official RSS URL.
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15"
                ),
                "Cookie": "CONSENT=YES+",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> NewsClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_query(self, query: str, *, category: str) -> list[NewsHeadline]:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        try:
            response = http_get(self._http, self._bucket, NEWS_RSS_URL, params=params)
        except httpx.HTTPError as exc:
            raise NewsHttpError(f"{category}: request failed ({exc.__class__.__name__})") from exc
        if response.status_code == 429:
            raise NewsHttpError(f"{category}: RSS rate limited", status_code=429)
        if response.status_code >= 400:
            raise NewsHttpError(
                f"{category}: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return headlines_from_rss(response.text, category=category, query=query)
        except NewsParseError:
            raise
        except Exception as exc:
            raise NewsParseError(f"{category}: RSS parse failed") from exc
