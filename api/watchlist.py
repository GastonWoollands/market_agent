from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from api.schemas import (
    WatchlistMember,
    WatchlistPoint,
    WatchlistResponse,
    WatchlistSparkPoint,
)
from store.display import resolve_change_pct, resolve_price
from store.repos import LiveTapeRow
from store.tickers import tv_symbol

SPARKLINE_BARS = 63
_QUOTE_STALE_AFTER = timedelta(days=3)


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def build_watchlist(
    rows: list[LiveTapeRow],
    *,
    sparklines: dict[str, list[tuple[date, Decimal]]],
    intraday: dict[str, list[tuple[datetime, Decimal]]],
    selected: str | None,
    now: datetime | None = None,
) -> WatchlistResponse:
    clock = now or datetime.now(UTC)
    members: list[WatchlistMember] = []
    for row in rows:
        price = resolve_price(row.quote_price, row.last_close)
        change_pct = resolve_change_pct(row.quote_change_pct, row.last_close, row.prev_close)
        spark = [
            WatchlistSparkPoint(date=day, value=round(float(close), 4))
            for day, close in sparklines.get(row.ticker, [])[-SPARKLINE_BARS:]
        ]
        intra = [
            WatchlistPoint(ts=ts, value=round(float(close), 4))
            for ts, close in intraday.get(row.ticker, [])
        ]
        members.append(
            WatchlistMember(
                ticker=row.ticker,
                name=row.name,
                price=_to_float(price),
                change_pct=_to_float(change_pct),
                market_state=row.market_state,
                as_of=row.as_of,
                tv_symbol=tv_symbol(row.ticker),
                sparkline=spark,
                intraday=intra,
            )
        )

    wanted = selected.upper() if selected else None
    chosen = next((item.ticker for item in members if item.ticker == wanted), None)
    if chosen is None and members:
        chosen = members[0].ticker

    quote_times = [item.as_of for item in members if item.as_of is not None]
    as_of = max(quote_times) if quote_times else None
    stale = as_of is None or (_aware(clock) - _aware(as_of) > _QUOTE_STALE_AFTER)
    return WatchlistResponse(
        as_of=as_of,
        stale=stale,
        selected=chosen,
        members=members,
    )
