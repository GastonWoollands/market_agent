from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from analytics.lookback import chart_window, window_deltas
from analytics.risk_on import CYCLICALS, DEFENSIVES, compute_risk_on
from api.schemas import (
    LiveDeltas,
    LiveDrilldown,
    LiveMacro,
    LiveOdds,
    LiveOddsOutcome,
    LivePoint,
    LiveQuote,
    LiveResponse,
    LiveRiskOn,
    LiveWatch,
)
from store.catalog import FredSeriesFile, PolymarketFile, UniversesFile
from store.display import resolve_change_pct, resolve_level_change, resolve_price
from store.models import OddsSnapshot
from store.repos import LiveMacroRow, LiveTapeRow

DEFAULT_LEVER = "DGS10"
HISTORY_DAYS = 400
THIN_LIQUIDITY = Decimal("10000")
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
    lever: str = DEFAULT_LEVER,
    history: list[tuple[date, Decimal]] | None = None,
    risk_on: LiveRiskOn | None = None,
    odds_rows: list[OddsSnapshot] | None = None,
    polymarket: PolymarketFile | None = None,
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
        drilldown=_drilldown(lever, history or [], fred, rows) if fred is not None else None,
        risk_on=risk_on,
        odds=_odds_items(odds_rows or [], polymarket),
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


def resolve_lever(requested: str | None, fred: FredSeriesFile) -> str:
    ids = {item.id for item in fred.series}
    if requested and requested in ids:
        return requested
    if DEFAULT_LEVER in ids:
        return DEFAULT_LEVER
    return fred.series[0].id if fred.series else DEFAULT_LEVER


def _drilldown(
    lever: str,
    history: list[tuple[date, Decimal]],
    fred: FredSeriesFile,
    tape_rows: list[LiveTapeRow],
) -> LiveDrilldown | None:
    meta = next((item for item in fred.series if item.id == lever), None)
    if meta is None:
        return None
    d1, w1, m1, y1 = window_deltas(history)
    last = history[-1] if history else None
    by_ticker = {row.ticker: row for row in tape_rows}
    watch: list[LiveWatch] = []
    for ticker in meta.watch:
        row = by_ticker.get(ticker)
        quote = _quote_from_row(
            ticker=ticker,
            name=row.name if row else ticker,
            role=None,
            row=row,
        )
        watch.append(LiveWatch(ticker=quote.ticker, name=quote.name, change_pct=quote.change_pct))
    points: list[LivePoint] = []
    for day, value in chart_window(history):
        number = _to_float(value)
        if number is None:
            continue
        points.append(LivePoint(date=day, value=number))
    return LiveDrilldown(
        series_id=meta.id,
        name=meta.name,
        unit=meta.unit,
        insight=meta.insight,
        as_of=last[0] if last else None,
        value=_to_float(last[1]) if last else None,
        deltas=LiveDeltas(
            d1=_to_float(d1),
            w1=_to_float(w1),
            m1=_to_float(m1),
            y1=_to_float(y1),
        ),
        points=points,
        watch=watch,
    )


def _as_float_series(points: list[tuple[date, Decimal]]) -> list[tuple[date, float]]:
    return [(day, float(value)) for day, value in points]


def risk_on_from_store(
    closes: dict[str, list[tuple[date, Decimal]]],
    vix: list[tuple[date, Decimal]],
    curve: list[tuple[date, Decimal]],
    *,
    now: date | None = None,
) -> LiveRiskOn:
    result = compute_risk_on(
        vix=_as_float_series(vix),
        hyg=_as_float_series(closes.get("HYG", [])),
        lqd=_as_float_series(closes.get("LQD", [])),
        rsp=_as_float_series(closes.get("RSP", [])),
        spy=_as_float_series(closes.get("SPY", [])),
        curve=_as_float_series(curve),
        cyclicals={name: _as_float_series(closes.get(name, [])) for name in CYCLICALS},
        defensives={name: _as_float_series(closes.get(name, [])) for name in DEFENSIVES},
        now=now,
    )
    return LiveRiskOn(
        score=None if result.score is None else round(result.score, 4),
        as_of=result.as_of,
        stale=result.stale,
        factors={
            name: None if value is None else round(value, 4)
            for name, value in result.factors.items()
        },
    )


def _odds_items(rows: list[OddsSnapshot], catalog: PolymarketFile | None) -> list[LiveOdds]:
    if catalog is None:
        return []
    by_slug = {row.slug: row for row in rows}
    items: list[LiveOdds] = []
    for event in catalog.events:
        if not event.show_on_live:
            continue
        row = by_slug.get(event.slug)
        if row is None:
            continue
        raw = row.raw or {}
        if raw.get("closed"):
            continue
        outcomes: list[LiveOddsOutcome] = []
        for market in raw.get("markets") or []:
            if not isinstance(market, dict) or market.get("yes") is None:
                continue
            yes = _to_float(Decimal(str(market["yes"])))
            if yes is None:
                continue
            outcomes.append(
                LiveOddsOutcome(
                    label=str(market.get("question") or event.label),
                    implied_yes=yes,
                )
            )
        outcomes.sort(key=lambda item: item.implied_yes, reverse=True)
        items.append(
            LiveOdds(
                slug=event.slug,
                label=event.label,
                category=event.category,
                question=row.question,
                implied_yes=_to_float(row.implied_yes),
                liquidity=_to_float(row.liquidity),
                thin=row.liquidity is not None and row.liquidity < THIN_LIQUIDITY,
                as_of=row.as_of,
                outcomes=outcomes,
            )
        )
    return items
