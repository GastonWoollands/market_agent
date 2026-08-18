from __future__ import annotations

from typing import Any

import httpx

from ingest.polymarket.errors import PolymarketHttpError, PolymarketParseError
from ingest.polymarket.parse import snapshot_from_event
from ingest.retry import http_get
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import OddsPoint

GAMMA_BASE = "https://gamma-api.polymarket.com"


class PolymarketClient:
    """Official Gamma event-by-slug API. Do not scrape polymarket.com or add a CLOB SDK."""

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
            headers={"Accept": "application/json", "User-Agent": "MarketAgent/0.1"},
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> PolymarketClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_event(self, slug: str) -> OddsPoint:
        payload = self._get(f"/events/slug/{slug}")
        if not isinstance(payload, dict):
            raise PolymarketParseError(f"{slug}: unexpected JSON payload")
        return snapshot_from_event(slug, payload)

    def search_events(self, query: str) -> list[dict[str, Any]]:
        payload = self._get("/public-search", params={"q": query})
        if isinstance(payload, dict):
            events = payload.get("events") or []
            return events if isinstance(events, list) else []
        return []

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        try:
            response = http_get(self._http, self._bucket, f"{GAMMA_BASE}{path}", params=params)
        except httpx.HTTPError as exc:
            raise PolymarketHttpError(f"{path}: request failed ({exc.__class__.__name__})") from exc
        if response.status_code == 429:
            raise PolymarketHttpError("Gamma rate limited", status_code=429)
        if response.status_code == 404:
            raise PolymarketHttpError(f"{path}: not found", status_code=404)
        if response.status_code >= 400:
            raise PolymarketHttpError(
                f"{path}: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise PolymarketParseError(f"{path}: response is not JSON") from exc
