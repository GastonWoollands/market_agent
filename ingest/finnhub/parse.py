from __future__ import annotations

from datetime import date
from typing import Any

from ingest.finnhub.errors import FinnhubParseError
from store.canonical import CalendarEvent

HOUR_LABEL = {
    "bmo": "before open",
    "amc": "after close",
    "dmh": "during market",
}


def events_from_earnings(
    payload: dict[str, Any],
    *,
    allowed: set[str] | None = None,
) -> list[CalendarEvent]:
    rows = payload.get("earningsCalendar")
    if not isinstance(rows, list):
        raise FinnhubParseError("earningsCalendar missing")
    wanted = {item.upper() for item in allowed} if allowed else None
    out: list[CalendarEvent] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if wanted is not None and symbol not in wanted:
            continue
        try:
            day = date.fromisoformat(str(row.get("date", ""))[:10])
        except ValueError:
            continue
        slug = f"finnhub:{symbol}:{day.isoformat()}"
        if slug in seen:
            continue
        seen.add(slug)
        hour = str(row.get("hour") or "").lower()
        when = HOUR_LABEL.get(hour)
        title = f"{symbol} earnings" + (f" ({when})" if when else "")
        extra = {
            "hour": hour or None,
            "eps_estimate": row.get("epsEstimate"),
            "revenue_estimate": row.get("revenueEstimate"),
            "quarter": row.get("quarter"),
            "year": row.get("year"),
        }
        out.append(
            CalendarEvent(
                slug=slug,
                date=day,
                title=title,
                kind="earnings",
                source="finnhub",
                ticker=symbol,
                extra=extra,
            )
        )
    return out
