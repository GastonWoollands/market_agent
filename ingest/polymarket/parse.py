from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.polymarket.errors import PolymarketParseError
from store.canonical import OddsPoint


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PolymarketParseError("outcomes/prices are not JSON") from exc
        return parsed if isinstance(parsed, list) else []
    return []


def _dec(value: Any) -> Decimal | None:
    if value in (None, "", "."):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _as_of(payload: dict[str, Any]) -> datetime:
    raw = payload.get("updatedAt") or payload.get("createdAt")
    if isinstance(raw, str) and raw:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _yes_price(labels: list[Any], prices: list[Any]) -> Decimal | None:
    pairs = list(zip(labels, prices, strict=False))
    for label, price in pairs:
        if str(label).strip().lower() == "yes":
            return _dec(price)
    parsed = [_dec(price) for price in prices]
    usable = [item for item in parsed if item is not None]
    return max(usable) if usable else None


def _open_markets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    markets = payload.get("markets") or []
    if not isinstance(markets, list):
        return []
    open_markets: list[dict[str, Any]] = []
    for market in markets:
        if not isinstance(market, dict):
            continue
        if market.get("closed") is True:
            continue
        if market.get("active") is False:
            continue
        open_markets.append(market)
    return open_markets


def snapshot_from_event(slug: str, payload: dict[str, Any]) -> OddsPoint:
    if not isinstance(payload, dict) or not payload:
        raise PolymarketParseError(f"{slug}: empty event")
    if payload.get("closed") is True:
        raise PolymarketParseError(f"{slug}: event is closed")
    markets = _open_markets(payload)
    if not markets:
        raise PolymarketParseError(f"{slug}: no open markets")

    compact: list[dict[str, Any]] = []
    best: tuple[Decimal, dict[str, Any], str] | None = None
    for market in markets:
        labels = _as_list(market.get("outcomes"))
        prices = _as_list(market.get("outcomePrices"))
        yes = _yes_price(labels, prices)
        if yes is None:
            continue
        question = str(market.get("question") or payload.get("title") or slug)
        compact.append(
            {
                "question": question,
                "yes": str(yes),
                "liquidity": market.get("liquidityNum") or market.get("liquidity"),
            }
        )
        if best is None or yes > best[0]:
            best = (yes, market, question)
    if best is None:
        raise PolymarketParseError(f"{slug}: no usable outcome prices")

    implied_yes, _market, question = best
    liquidity = _dec(payload.get("liquidity")) or _dec(payload.get("liquidityNum"))
    title = str(payload.get("title") or question)
    return OddsPoint(
        slug=slug,
        question=title,
        implied_yes=implied_yes,
        liquidity=liquidity,
        as_of=_as_of(payload),
        raw={
            "title": title,
            "closed": bool(payload.get("closed")),
            "active": payload.get("active"),
            "markets": compact,
        },
    )
