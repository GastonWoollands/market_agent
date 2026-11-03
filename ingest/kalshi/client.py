from __future__ import annotations

from ingest.http import JsonApiClient
from ingest.kalshi.errors import KalshiHttpError, KalshiParseError
from ingest.kalshi.parse import events_from_payload
from store.canonical import KalshiEvent


class KalshiClient(JsonApiClient):
    """Kalshi public trade API v2, read endpoints only. No account, no order routes."""

    base_url = "https://api.elections.kalshi.com/trade-api/v2"
    name = "Kalshi"
    http_error = KalshiHttpError
    parse_error = KalshiParseError

    def open_events(self, series: str, *, limit: int = 10) -> list[KalshiEvent]:
        """Open events of a series with their open markets, soonest strike date first."""
        payload = self.get_json(
            "/events",
            params={
                "series_ticker": series,
                "status": "open",
                "with_nested_markets": "true",
                "limit": limit,
            },
        )
        return events_from_payload(payload)
