from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from ingest.yahoo.errors import YahooParseError
from store.canonical import DailyBar, QuoteSnapshot


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except Exception:
        return None
    return Decimal(str(value))


def _session_date(index_value: Any) -> date:
    ts = getattr(index_value, "to_pydatetime", lambda: index_value)()
    if isinstance(ts, datetime):
        return ts.date()
    return date.fromisoformat(str(index_value)[:10])


def _as_of(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        converted = to_pydatetime()
        if isinstance(converted, datetime):
            if converted.tzinfo is None:
                return converted.replace(tzinfo=UTC)
            return converted.astimezone(UTC)
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return datetime.fromtimestamp(float(timestamp()), tz=UTC)
    return datetime.fromtimestamp(int(value), tz=UTC)


def _row_get(row: Any, *names: str) -> Any:
    for name in names:
        if name in row.index:
            value = row[name]
            if value is not None:
                return value
    return None


def bars_from_history(frame: Any, symbol: str) -> list[DailyBar]:
    if frame is None or getattr(frame, "empty", True):
        raise YahooParseError(f"{symbol}: history is empty")

    bars: list[DailyBar] = []
    seen: set[date] = set()
    for index_value, row in frame.iterrows():
        close = _dec(_row_get(row, "Close", "close"))
        if close is None:
            continue
        session_date = _session_date(index_value)
        if session_date in seen:
            continue
        seen.add(session_date)
        adj = _dec(_row_get(row, "Adj Close", "AdjClose", "adjclose")) or close
        volume_raw = _row_get(row, "Volume", "volume")
        volume = int(volume_raw) if volume_raw is not None and volume_raw == volume_raw else 0
        bars.append(
            DailyBar(
                yahoo_symbol=symbol,
                date=session_date,
                open=_dec(_row_get(row, "Open", "open")) or close,
                high=_dec(_row_get(row, "High", "high")) or close,
                low=_dec(_row_get(row, "Low", "low")) or close,
                close=close,
                adj_close=adj,
                volume=volume,
            )
        )
    if not bars:
        raise YahooParseError(f"{symbol}: no usable daily bars")
    return bars


def snapshot_from_chart_meta(symbol: str, meta: dict[str, Any] | None) -> QuoteSnapshot | None:
    payload = meta or {}
    price = _dec(payload.get("regularMarketPrice"))
    if price is None:
        return None
    prev = _dec(payload.get("chartPreviousClose")) or _dec(payload.get("previousClose"))
    change_pct = None
    if prev is not None and prev != 0:
        change_pct = (price / prev - 1) * Decimal("100")
    as_of = _as_of(payload.get("regularMarketTime"))
    volume_raw = payload.get("regularMarketVolume")
    return QuoteSnapshot(
        yahoo_symbol=symbol,
        price=price,
        change_pct=change_pct,
        volume=int(volume_raw) if volume_raw is not None else None,
        market_state=payload.get("marketState"),
        as_of=as_of,
    )
