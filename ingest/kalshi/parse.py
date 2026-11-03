from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.kalshi.errors import KalshiParseError
from store.canonical import KalshiEvent, KalshiMarket


def events_from_payload(payload: Any) -> list[KalshiEvent]:
    """`GET /events?with_nested_markets=true` -> open events, soonest strike date first."""
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise KalshiParseError("events payload has no `events` list")
    events = [_event(item) for item in payload["events"]]
    return sorted(events, key=lambda event: (event.strike_date is None, event.strike_date))


def _event(item: Any) -> KalshiEvent:
    if not isinstance(item, dict):
        raise KalshiParseError("event is not an object")
    ticker = _required(item, "event_ticker")
    markets = item.get("markets") or []
    return KalshiEvent(
        ticker=ticker,
        series=_required(item, "series_ticker"),
        title=_required(item, "title"),
        sub_title=str(item.get("sub_title") or ""),
        strike_date=_time(item.get("strike_date")),
        markets=tuple(_market(ticker, market) for market in markets if _is_open(market)),
    )


def _market(event: str, item: dict[str, Any]) -> KalshiMarket:
    return KalshiMarket(
        ticker=_required(item, "ticker"),
        label=str(item.get("yes_sub_title") or item.get("subtitle") or item["ticker"]),
        strike_type=item.get("strike_type"),
        floor_strike=_dec(item.get("floor_strike")),
        cap_strike=_dec(item.get("cap_strike")),
        yes_bid=_dec(item.get("yes_bid_dollars")),
        yes_ask=_dec(item.get("yes_ask_dollars")),
        last_price=_dec(item.get("last_price_dollars")),
        volume=_dec(item.get("volume_fp")) or Decimal(0),
        open_interest=_dec(item.get("open_interest_fp")) or Decimal(0),
    )


def _is_open(item: Any) -> bool:
    return isinstance(item, dict) and item.get("status") in ("active", "open")


def _required(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not value:
        raise KalshiParseError(f"missing `{key}`")
    return str(value)


def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise KalshiParseError(f"not a number: {value!r}") from exc


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
