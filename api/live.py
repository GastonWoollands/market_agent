from datetime import UTC, datetime, timedelta
from decimal import Decimal

from api.schemas import LiveMacro, LiveQuote, LiveResponse
from store.catalog import FredSeriesFile, UniversesFile
from store.display import resolve_change_pct, resolve_level_change, resolve_price
from store.repos import LiveMacroRow, LiveTapeRow

_QUOTE_STALE_AFTER = timedelta(days=3)
_STATE_RANK = {
    "REGULAR": 0,
    "PRE": 1,
    "PREPRE": 2,
    "POST": 3,
    "POSTPOST": 4,
    "CLOSED": 5,
}


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _quote_from_row(
    *,
    ticker: str,
    name: str,
    role: str | None,
    row: LiveTapeRow | None,
) -> LiveQuote:
    if row is None:
        return LiveQuote(ticker=ticker, name=name, role=role)
    price = resolve_price(row.quote_price, row.last_close)
    change_pct = resolve_change_pct(row.quote_change_pct, row.last_close, row.prev_close)
    return LiveQuote(
        ticker=ticker,
        name=name,
        role=role,
        price=_to_float(price),
        change_pct=_to_float(change_pct),
        market_state=row.market_state,
        as_of=row.as_of,
    )


def _session_state(quotes: list[LiveQuote]) -> str | None:
    best: tuple[int, str] | None = None
    for quote in quotes:
        if not quote.market_state:
            continue
        rank = _STATE_RANK.get(quote.market_state.upper())
        if rank is None:
            continue
        if best is None or rank < best[0]:
            best = (rank, quote.market_state)
    return None if best is None else best[1]


def _is_stale(as_of: datetime | None, now: datetime) -> bool:
    if as_of is None:
        return True
    return _aware(now) - _aware(as_of) > _QUOTE_STALE_AFTER


def build_live(
    rows: list[LiveTapeRow],
    catalog: UniversesFile,
    *,
    now: datetime | None = None,
    macro_rows: list[LiveMacroRow] | None = None,
    fred: FredSeriesFile | None = None,
) -> LiveResponse:
    clock = now or datetime.now(UTC)
    by_ticker = {row.ticker: row for row in rows}
    tape_meta = {item.ticker: item for item in catalog.tape.instruments}

    header: list[LiveQuote] = []
    for item in catalog.live.header:
        row = by_ticker.get(item.ticker)
        meta = tape_meta.get(item.ticker)
        name = item.label or (row.name if row else None) or (meta.name if meta else item.ticker)
        role = meta.role if meta else None
        header.append(_quote_from_row(ticker=item.ticker, name=name, role=role, row=row))

    mover_roles = set(catalog.live.mover_roles)
    movers: list[LiveQuote] = []
    for meta in catalog.tape.instruments:
        if meta.role not in mover_roles:
            continue
        row = by_ticker.get(meta.ticker)
        movers.append(
            _quote_from_row(
                ticker=meta.ticker,
                name=meta.name,
                role=meta.role,
                row=row,
            )
        )

    quote_times = [item.as_of for item in header if item.as_of is not None]
    as_of = max(quote_times) if quote_times else None
    return LiveResponse(
        as_of=as_of,
        market_state=_session_state(header),
        stale=_is_stale(as_of, clock),
        header=header,
        movers=movers,
        macro=_macro_items(macro_rows or [], fred),
    )


def _macro_items(rows: list[LiveMacroRow], fred: FredSeriesFile | None) -> list[LiveMacro]:
    if fred is None:
        return []
    by_id = {row.series_id: row for row in rows}
    items: list[LiveMacro] = []
    for item in fred.series:
        row = by_id.get(item.id)
        last = row.last if row else None
        prev = row.prev if row else None
        items.append(
            LiveMacro(
                series_id=item.id,
                name=item.name,
                unit=item.unit,
                category=item.category,
                frequency=item.frequency,
                value=_to_float(last),
                change=_to_float(resolve_level_change(last, prev)),
                as_of=row.last_date if row else None,
            )
        )
    return items
