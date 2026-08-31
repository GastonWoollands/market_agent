from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from analytics.lookback import chart_window, window_deltas
from analytics.risk_on import CYCLICALS, DEFENSIVES, compute_risk_on
from api.schemas import (
    LiveAnomaly,
    LiveBrief,
    LiveCoMove,
    LiveDeltas,
    LiveDrilldown,
    LiveEvent,
    LiveLiquidity,
    LiveMacro,
    LiveOdds,
    LiveOddsOutcome,
    LiveOutlier,
    LivePoint,
    LiveQuote,
    LiveRegime,
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
_CHANGE_KIND = {
    "REGULAR": "session",
    "PRE": "gap",
    "PREPRE": "gap",
    "POST": "after_hours",
    "POSTPOST": "after_hours",
    "CLOSED": "close",
}
WATCHLIST_OUTLIERS = 3


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _scaled_macro(value: Decimal | None, scale: float) -> Decimal | None:
    if value is None or scale == 1:
        return value
    return value * Decimal(str(scale))


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
    state = row.market_state.upper() if row.market_state else None
    return LiveQuote(
        ticker=ticker,
        name=name,
        role=role,
        price=_to_float(price),
        change_pct=_to_float(change_pct),
        change_kind=_CHANGE_KIND.get(state) if state else None,
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
    regime: LiveRegime | None = None,
    liquidity: LiveLiquidity | None = None,
    anomalies: list[LiveAnomaly] | None = None,
    odds_rows: list[OddsSnapshot] | None = None,
    polymarket: PolymarketFile | None = None,
    events: list[LiveEvent] | None = None,
    brief: LiveBrief | None = None,
    outliers: list[LiveOutlier] | None = None,
    co_moves: list[LiveCoMove] | None = None,
    watchlist_rows: list[LiveTapeRow] | None = None,
) -> LiveResponse:
    clock = now or datetime.now(UTC)
    by_ticker = {row.ticker: row for row in rows}
    tape_meta = {item.ticker: item for item in catalog.tape.instruments}

    def _quotes_for(items: list) -> list[LiveQuote]:
        out: list[LiveQuote] = []
        for item in items:
            row = by_ticker.get(item.ticker)
            meta = tape_meta.get(item.ticker)
            name = (
                item.label or (row.name if row else None) or (meta.name if meta else item.ticker)
            )
            role = meta.role if meta else None
            out.append(_quote_from_row(ticker=item.ticker, name=name, role=role, row=row))
        return out

    header = _quotes_for(catalog.live.header)
    intl = _quotes_for(catalog.live.intl_section)

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
    movers.sort(key=lambda item: (item.change_pct is None, -(item.change_pct or 0.0), item.ticker))

    quote_times = [item.as_of for item in header if item.as_of is not None]
    as_of = max(quote_times) if quote_times else None
    return LiveResponse(
        as_of=as_of,
        market_state=_session_state(header),
        stale=_is_stale(as_of, clock),
        header=header,
        intl=intl,
        movers=movers,
        macro=_macro_items(macro_rows or [], fred),
        drilldown=_drilldown(lever, history or [], fred, rows) if fred is not None else None,
        risk_on=risk_on,
        regime=regime,
        liquidity=liquidity,
        anomalies=list(anomalies or []),
        odds=_odds_items(odds_rows or [], polymarket),
        events=list(events or []),
        brief=brief,
        outliers=list(outliers or []),
        co_moves=list(co_moves or []),
        watchlist_outliers=_watchlist_outliers(watchlist_rows or []),
    )


def _watchlist_outliers(rows: list[LiveTapeRow]) -> list[LiveQuote]:
    quotes = [
        _quote_from_row(ticker=row.ticker, name=row.name, role=None, row=row) for row in rows
    ]
    quotes.sort(
        key=lambda item: (item.change_pct is None, -abs(item.change_pct or 0.0), item.ticker)
    )
    return quotes[:WATCHLIST_OUTLIERS]


def live_brief(report: object | None) -> LiveBrief | None:
    if report is None:
        return None
    body = getattr(report, "body_json", None)
    if not isinstance(body, dict):
        body = {}
    headline = body.get("headline") if isinstance(body.get("headline"), str) else None
    live_md = body.get("live_md") if isinstance(body.get("live_md"), str) else None
    expect = body.get("expect") if isinstance(body.get("expect"), str) else None
    if not headline and not live_md and not expect:
        return None
    return LiveBrief(
        headline=headline,
        live_md=live_md,
        expect=expect,
        as_of=getattr(report, "as_of", None),
        status=getattr(report, "status", None),
    )


def live_event_models(rows: list[dict[str, object]]) -> list[LiveEvent]:
    out: list[LiveEvent] = []
    for row in rows:
        raw_date = row.get("date")
        title = str(row.get("title") or "")
        kind = str(row.get("kind") or "")
        source = str(row.get("source") or "")
        if not title or not kind:
            continue
        try:
            day = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            continue
        ticker = row.get("ticker")
        out.append(
            LiveEvent(
                date=day,
                title=title,
                kind=kind,
                ticker=str(ticker) if ticker else None,
                source=source,
            )
        )
    return out


def outlier_models(rows: list[dict[str, object]]) -> list[LiveOutlier]:
    return [LiveOutlier.model_validate(row) for row in rows if row.get("id")]


def co_move_models(rows: list[dict[str, object]]) -> list[LiveCoMove]:
    return [LiveCoMove.model_validate(row) for row in rows if row.get("ids")]


def regime_model(row: object | None) -> LiveRegime | None:
    """Map a stored RegimeSnapshot ORM row to the Live schema."""
    if row is None:
        return None

    def _conf(value: object) -> float | None:
        return None if value is None else round(float(value), 2)  # type: ignore[arg-type]

    return LiveRegime(
        as_of=getattr(row, "as_of", None),
        growth=getattr(row, "growth_regime", None),
        inflation=getattr(row, "inflation_regime", None),
        policy=getattr(row, "policy_regime", None),
        volatility=getattr(row, "volatility_regime", None),
        growth_confidence=_conf(getattr(row, "growth_confidence", None)),
        inflation_confidence=_conf(getattr(row, "inflation_confidence", None)),
        policy_confidence=_conf(getattr(row, "policy_confidence", None)),
        volatility_confidence=_conf(getattr(row, "volatility_confidence", None)),
    )


def liquidity_model(data: dict[str, object] | None) -> LiveLiquidity | None:
    """Map the compute_net_liquidity dict to the Live schema. Flattens components."""
    if not data:
        return None
    components = data.get("components") or {}
    if not isinstance(components, dict):
        components = {}
    return LiveLiquidity(
        net_liquidity_bn=_maybe_float(data.get("net_liquidity_bn")),
        wow_change_bn=_maybe_float(data.get("wow_change_bn")),
        fed_bs_bn=_maybe_float(components.get("fed_bs_bn")),
        rrp_bn=_maybe_float(components.get("rrp_bn")),
        tga_bn=_maybe_float(components.get("tga_bn")),
    )


def anomaly_models(items: list[object] | None) -> list[LiveAnomaly]:
    """Map analytics.anomaly_detect.Anomaly objects to the Live schema."""
    out: list[LiveAnomaly] = []
    for item in items or []:
        desc = getattr(item, "description", None)
        kind = getattr(item, "type", None)
        if not desc or not kind:
            continue
        out.append(
            LiveAnomaly(
                type=str(kind),
                description=str(desc),
                severity=round(float(getattr(item, "severity", 0.0)), 2),
            )
        )
    return out


def _maybe_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    return None


LIQUIDITY_SERIES = ("WALCL", "RRPONTSYD", "WTREGEN")


def net_liquidity_from_store(
    points_by_series: dict[str, list[tuple[date, Decimal]]],
) -> dict[str, object] | None:
    """Build compute_net_liquidity() rows from stored FRED points (value + 1w delta)."""
    from analytics.macro_pack import compute_net_liquidity

    rows: list[dict[str, object]] = []
    for series_id in LIQUIDITY_SERIES:
        points = points_by_series.get(series_id) or []
        if not points:
            return None
        _d1, w1, _m1, _y1 = window_deltas([(day, value) for day, value in points])
        rows.append(
            {
                "series_id": series_id,
                "value": float(points[-1][1]),
                "w1": float(w1) if w1 is not None else None,
            }
        )
    return compute_net_liquidity(rows)


def _macro_items(rows: list[LiveMacroRow], fred: FredSeriesFile | None) -> list[LiveMacro]:
    if fred is None:
        return []
    by_id = {row.series_id: row for row in rows}
    items: list[LiveMacro] = []
    for item in fred.series:
        if not item.show_on_live:
            continue
        row = by_id.get(item.id)
        last = _scaled_macro(row.last if row else None, item.scale)
        prev = _scaled_macro(row.prev if row else None, item.scale)
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
                spine=item.spine,
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
    if meta.scale != 1:
        factor = Decimal(str(meta.scale))
        history = [(day, value * factor) for day, value in history]
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
