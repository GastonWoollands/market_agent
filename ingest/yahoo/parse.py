from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from ingest.yahoo.errors import YahooParseError
from store.canonical import (
    DailyBar,
    IntradayBar,
    OptionQuote,
    OptionUnderlying,
    QuoteSnapshot,
)

ET = ZoneInfo("America/New_York")


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


def bars_from_intraday(frame: Any, symbol: str, interval: str) -> list[IntradayBar]:
    if frame is None or getattr(frame, "empty", True):
        raise YahooParseError(f"{symbol}: intraday is empty")

    bars: list[IntradayBar] = []
    seen: set[datetime] = set()
    for index_value, row in frame.iterrows():
        close = _dec(_row_get(row, "Close", "close"))
        if close is None:
            continue
        ts = _as_of(index_value)
        if ts in seen:
            continue
        seen.add(ts)
        volume_raw = _row_get(row, "Volume", "volume")
        volume = int(volume_raw) if volume_raw is not None and volume_raw == volume_raw else 0
        bars.append(
            IntradayBar(
                yahoo_symbol=symbol,
                ts=ts,
                interval=interval,
                open=_dec(_row_get(row, "Open", "open")) or close,
                high=_dec(_row_get(row, "High", "high")) or close,
                low=_dec(_row_get(row, "Low", "low")) or close,
                close=close,
                volume=volume,
            )
        )
    if not bars:
        raise YahooParseError(f"{symbol}: no usable intraday bars")
    return bars


def listing_from_chart_meta(symbol: str, meta: dict[str, Any] | None) -> tuple[str, str | None]:
    payload = meta or {}
    name = str(payload.get("shortName") or payload.get("longName") or symbol).strip()
    exchange = payload.get("exchangeName")
    exchange_s = str(exchange).strip() if exchange else None
    return name or symbol, exchange_s or None


def snapshot_from_chart_meta(symbol: str, meta: dict[str, Any] | None) -> QuoteSnapshot | None:
    payload = meta or {}
    price = _dec(payload.get("regularMarketPrice"))
    if price is None:
        return None
    prev = (
        _dec(payload.get("previousClose"))
        or _dec(payload.get("regularMarketPreviousClose"))
        or _dec(payload.get("chartPreviousClose"))
    )
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


def option_quotes_from_frame(
    frame: Any, symbol: str, expiry: date, kind: str
) -> list[OptionQuote]:
    """One side of `option_chain(expiry)`. Rows without a strike are dropped."""
    if frame is None or getattr(frame, "empty", True):
        return []
    quotes: list[OptionQuote] = []
    for row in frame.to_dict("records"):
        strike = _dec(row.get("strike"))
        if strike is None or strike <= 0:
            continue
        last_trade = row.get("lastTradeDate")
        quotes.append(
            OptionQuote(
                symbol=symbol,
                expiry=expiry,
                kind=kind,
                strike=strike,
                bid=_dec(row.get("bid")),
                ask=_dec(row.get("ask")),
                last=_dec(row.get("lastPrice")),
                volume=_int(row.get("volume")),
                open_interest=_int(row.get("openInterest")),
                vendor_iv=_dec(row.get("impliedVolatility")),
                last_trade_at=_optional_as_of(last_trade),
            )
        )
    return quotes


def underlying_from_quote(symbol: str, quote: dict[str, Any] | None) -> OptionUnderlying:
    """Spot, quote time, dividend yield and the next earnings date from the chain's quote."""
    quote = quote or {}
    spot = _dec(quote.get("regularMarketPrice"))
    stamp = quote.get("regularMarketTime")
    if spot is None or spot <= 0 or not isinstance(stamp, int | float):
        raise YahooParseError(f"{symbol}: option chain has no underlying price")
    quote_at = datetime.fromtimestamp(stamp, tz=UTC)
    as_of = quote_at.astimezone(ET).date()
    dividend = _dec(quote.get("dividendYield"))  # percent on this endpoint
    earnings: date | None = None
    for key in ("earningsTimestamp", "earningsTimestampStart"):
        value = quote.get(key)
        if isinstance(value, int | float):
            day = datetime.fromtimestamp(value, tz=UTC).astimezone(ET).date()
            if day >= as_of:
                earnings = day
                break
    estimate = quote.get("isEarningsDateEstimate")
    return OptionUnderlying(
        symbol=symbol,
        as_of=as_of,
        spot=spot,
        quote_at=quote_at,
        dividend_yield=None if dividend is None else dividend / 100,
        earnings_date=earnings,
        earnings_estimate=estimate if isinstance(estimate, bool) and earnings else None,
    )


def _int(value: Any) -> int | None:
    number = _dec(value)
    return None if number is None else int(number)


def _optional_as_of(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return _as_of(value)
    except Exception:
        return None
