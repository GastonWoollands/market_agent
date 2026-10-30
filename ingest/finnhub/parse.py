from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from ingest.finnhub.errors import FinnhubParseError
from store.canonical import CalendarEvent, NewsHeadline

WIRE_CATEGORY = "wire"
COMPANY_CATEGORY = "company"
SUMMARY_MAX = 400
_TERMINAL = (".", "!", "?", "…", '"', "”", ")")
_SPACE = re.compile(r"\s+")

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


def headlines_from_news(payload: Any, *, category: str, query: str) -> list[NewsHeadline]:
    """Finnhub news rows -> headlines. `summary` is None when it only repeats the headline."""
    if not isinstance(payload, list):
        raise FinnhubParseError("news: expected a JSON list")
    out: list[NewsHeadline] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        title = _clean(row.get("headline"))
        url = str(row.get("url") or "").strip()
        stamp = row.get("datetime")
        if not title or not url or not isinstance(stamp, int | float) or stamp <= 0:
            continue
        guid = f"finnhub:{row.get('id') or url}"
        if guid in seen:
            continue
        seen.add(guid)
        out.append(
            NewsHeadline(
                guid=guid,
                title=title,
                url=url,
                publisher=_clean(row.get("source")) or "Finnhub",
                published_at=datetime.fromtimestamp(stamp, UTC),
                category=category,
                query=query,
                summary=real_summary(title, row.get("summary")),
            )
        )
    return out


def real_summary(title: str, raw: Any) -> str | None:
    """Drop empty summaries and wire rows that just repeat the headline (+ source)."""
    text = _clean(raw)
    if not text:
        return None
    head = _clean(title.split(" - ")[0]).lower()
    if head and text.lower().startswith(head[: max(20, len(head) - 5)]):
        return None
    if len(text) > SUMMARY_MAX:
        text = text[: SUMMARY_MAX - 1].rsplit(" ", 1)[0] + "…"
    elif not text.endswith(_TERMINAL):
        text += "…"  # vendor cut it mid-sentence (Yahoo rows stop at ~100 chars)
    return text


def _clean(value: Any) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()
