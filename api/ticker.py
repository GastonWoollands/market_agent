"""Ticker and Compare pages: one name's desk metrics, history, technicals and risk.

Everything comes from Postgres. The only read-time math is on stored rows: technicals
and fallback risk on stored bars, EV for names outside the valuation universe, and the
desk ratios in `analytics/desk.py`. Compare reuses the per-name blocks so a number never
differs between the two pages.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from analytics.corr import paired_returns, pearson
from analytics.desk import (
    accrual_from_fy,
    fcf_yield,
    financing_gap,
    interest_coverage,
    nd_ebitda,
    share_change,
)
from analytics.risk import snapshot as risk_snapshot
from analytics.rrg import align_pair
from analytics.technicals import indexed, relative_return, technicals
from api.schemas import (
    CompareResponse,
    CompareRow,
    DynamicsCorr,
    DynamicsOverlay,
    DynamicsPoint,
    TickerDesk,
    TickerEvent,
    TickerFyRow,
    TickerIdentity,
    TickerNews,
    TickerPrice,
    TickerResponse,
    TickerRisk,
    TickerTechnicals,
    TickerTtmRow,
)
from store.catalog import load_universes
from store.repos import (
    adj_closes_for_instrument_ids,
    closes_for_instrument_ids,
    instrument_by_ticker,
    latest_risk_stats,
    latest_valuation_map,
    metric_fy_history,
    metric_ttm_history,
    news_for_name,
    opportunity_score_map,
    universes_for_instrument,
    upcoming_events_for_ticker,
)
from store.tickers import tv_symbol

BENCHMARK = "SPY"
STALE_AFTER_DAYS = 5
YEAR_AGO = (300, 430)
MAX_COMPARE = 6
NO_BARS_HINT = "No stored daily bars. Add the ticker to the Watchlist to hydrate it."
UNTRACKED_HINT = "Outside every universe: daily bars are not refreshed. Add it to the Watchlist."
LOOKBACK_DAYS = 400

Series = list[tuple[date, float]]


@dataclass
class NameInputs:
    instrument: Any
    universes: list[str] = field(default_factory=list)
    closes: Series = field(default_factory=list)
    adj_closes: Series = field(default_factory=list)
    ttm: list[Any] = field(default_factory=list)
    fy: list[Any] = field(default_factory=list)
    valuation: Any | None = None
    score: Any | None = None
    ranked: int = 0
    risk: Any | None = None
    events: list[Any] = field(default_factory=list)
    news: list[Any] = field(default_factory=list)


@dataclass
class Benchmarks:
    """Adjusted closes for SPY / QQQ and the sector ETFs, plus sector → ETF ticker."""

    adj: dict[str, Series] = field(default_factory=dict)
    sector_etf: dict[str, str] = field(default_factory=dict)


def build_ticker(item: NameInputs, bench: Benchmarks, *, today: date) -> TickerResponse:
    price = _price(item.closes)
    return TickerResponse(
        stale=price is None or (today - price.as_of).days > STALE_AFTER_DAYS,
        identity=_identity(item, bench),
        price=price,
        desk=_desk(item, price),
        ttm=[_ttm_row(row) for row in item.ttm],
        fy=[_fy_row(row) for row in item.fy],
        technicals=_technicals(item, bench),
        risk=_risk(item, bench),
        events=[TickerEvent(date=row.date, title=row.title, kind=row.kind) for row in item.events],
        news=[
            TickerNews(
                published_at=row.published_at,
                title=row.title,
                url=row.url,
                publisher=row.publisher,
            )
            for row in item.news
        ],
        hint=_hint(item),
    )


def _hint(item: NameInputs) -> str | None:
    if not item.closes:
        return NO_BARS_HINT
    if not item.universes:
        return UNTRACKED_HINT
    return None


def build_compare(
    items: Sequence[NameInputs],
    bench: Benchmarks,
    *,
    requested: Sequence[str],
    missing: Sequence[str],
    today: date,
) -> CompareResponse:
    rows: list[CompareRow] = []
    for item in items:
        price = _price(item.closes)
        rows.append(
            CompareRow(
                identity=_identity(item, bench),
                price=price,
                desk=_desk(item, price),
                technicals=_technicals(item, bench),
                risk=_risk(item, bench),
            )
        )
    as_of = max((row.price.as_of for row in rows if row.price), default=None)
    overlay = [
        DynamicsOverlay(ticker=item.instrument.ticker, name=item.instrument.name, points=points)
        for item in items
        if (points := _indexed_points(item.adj_closes))
    ]
    spy = _indexed_points(bench.adj.get(BENCHMARK, []))
    if spy and BENCHMARK not in {item.instrument.ticker for item in items}:
        overlay.append(DynamicsOverlay(ticker=BENCHMARK, name="S&P 500", points=spy))
    return CompareResponse(
        as_of=as_of,
        stale=as_of is None or (today - as_of).days > STALE_AFTER_DAYS,
        benchmark=BENCHMARK,
        tickers=list(requested),
        missing=list(missing),
        rows=rows,
        corr=_corr(items),
        overlay=overlay,
    )


def parse_tickers(raw: str) -> list[str]:
    out: list[str] = []
    for part in raw.split(","):
        ticker = part.strip().upper()
        if ticker and ticker not in out:
            out.append(ticker)
    return out[:MAX_COMPARE]


def _identity(item: NameInputs, bench: Benchmarks) -> TickerIdentity:
    inst = item.instrument
    sector = getattr(inst, "sector", None)
    return TickerIdentity(
        ticker=inst.ticker,
        name=inst.name,
        exchange=getattr(inst, "exchange", None),
        sector=sector,
        industry=getattr(inst, "industry", None),
        cik=getattr(inst, "cik", None),
        universes=item.universes,
        tv_symbol=tv_symbol(inst.ticker),
        sector_etf=bench.sector_etf.get(sector) if sector else None,
    )


def _price(closes: Series) -> TickerPrice | None:
    if not closes:
        return None
    day, close = closes[-1]
    change = None
    if len(closes) > 1 and closes[-2][1]:
        change = close / closes[-2][1] - 1.0
    return TickerPrice(as_of=day, close=close, change_1d=change)


def _desk(item: NameInputs, price: TickerPrice | None) -> TickerDesk | None:
    latest = item.ttm[-1] if item.ttm else None
    # valuation_daily is only refreshed for current members; a former member's row is stale.
    value = item.valuation if "valuation" in item.universes else None
    if latest is None and value is None:
        return None
    shares = _num(getattr(latest, "shares", None))
    net_debt = _num(getattr(latest, "net_debt", None))
    ebitda = _num(getattr(latest, "ebitda", None))
    market_cap = price.close * shares if price and shares else None
    ev = _num(getattr(value, "ev", None))
    basis = "valuation_daily" if ev is not None else None
    if ev is None and market_cap is not None and net_debt is not None:
        ev, basis = market_cap + net_debt, "read_time"
    multiple = _num(getattr(value, "ev_ebitda", None))
    if multiple is None and ev is not None and ebitda and ebitda > 0:
        multiple = ev / ebitda
    prior = _year_ago(item.ttm)
    score = item.score
    return TickerDesk(
        ttm_as_of=getattr(latest, "as_of", None),
        valuation_as_of=getattr(value, "as_of", None),
        ev_basis=basis,
        market_cap=market_cap,
        ev=ev,
        ev_ebitda=multiple,
        pctile_5y=_num(getattr(value, "pctile_5y", None)),
        comparable=bool(getattr(value, "comparable", False)),
        sample_size=getattr(value, "sample_size", None),
        fcf_yield=fcf_yield(getattr(latest, "fcf", None), ev),
        nd_ebitda=nd_ebitda(net_debt, ebitda),
        ebitda_growth_1y=_num(getattr(value, "ebitda_growth_1y", None))
        if value is not None
        else _growth(ebitda, _num(getattr(prior, "ebitda", None))),
        revenue_growth_1y=_growth(
            _num(getattr(latest, "revenue", None)), _num(getattr(prior, "revenue", None))
        ),
        interest_coverage=interest_coverage(
            getattr(latest, "ebit", None), getattr(latest, "interest_expense", None)
        ),
        share_change_1y=share_change(shares, getattr(prior, "shares", None)),
        financing_gap=financing_gap(
            getattr(latest, "capex", None), getattr(latest, "cfo", None), market_cap
        ),
        accrual=accrual_from_fy(item.fy[-1] if item.fy else None),
        rank=getattr(score, "rank", None),
        ranked=(item.ranked or None) if score is not None else None,
        trap=getattr(score, "trap", None),
    )


def _technicals(item: NameInputs, bench: Benchmarks) -> TickerTechnicals | None:
    snap = technicals(item.closes, item.adj_closes)
    if snap is None:
        return None
    spy = technicals(bench.adj.get(BENCHMARK, []), bench.adj.get(BENCHMARK, []))
    etf = bench.sector_etf.get(getattr(item.instrument, "sector", None) or "")
    sector = technicals(bench.adj.get(etf, []), bench.adj.get(etf, [])) if etf else None
    ret = snap.returns
    return TickerTechnicals(
        as_of=snap.as_of,
        sma_20=snap.sma.get(20),
        sma_50=snap.sma.get(50),
        sma_100=snap.sma.get(100),
        sma_200=snap.sma.get(200),
        vs_sma_20=snap.vs_sma.get(20),
        vs_sma_50=snap.vs_sma.get(50),
        vs_sma_100=snap.vs_sma.get(100),
        vs_sma_200=snap.vs_sma.get(200),
        rsi_14=snap.rsi_14,
        high_52w=snap.high_52w,
        low_52w=snap.low_52w,
        vs_high_52w=snap.vs_high_52w,
        ret_1w=ret.get("1w"),
        ret_1m=ret.get("1m"),
        ret_3m=ret.get("3m"),
        ret_6m=ret.get("6m"),
        ret_1y=ret.get("1y"),
        rel_spy_3m=relative_return(ret.get("3m"), spy.returns.get("3m") if spy else None),
        rel_spy_1y=relative_return(ret.get("1y"), spy.returns.get("1y") if spy else None),
        rel_sector_3m=relative_return(ret.get("3m"), sector.returns.get("3m") if sector else None),
        rel_sector_1y=relative_return(ret.get("1y"), sector.returns.get("1y") if sector else None),
    )


def _risk(item: NameInputs, bench: Benchmarks) -> TickerRisk | None:
    stored = item.risk
    if stored is not None:
        return TickerRisk(
            as_of=stored.as_of,
            source="risk_stats",
            sessions=stored.sessions,
            vol_3m=_num(stored.vol_3m),
            vol_1y=_num(stored.vol_1y),
            downside_vol_1y=_num(stored.downside_vol_1y),
            beta_spy=_num(stored.beta_spy),
            beta_qqq=_num(stored.beta_qqq),
            corr_spy=_num(stored.corr_spy),
            max_drawdown_1y=_num(stored.max_drawdown_1y),
            drawdown=_num(stored.drawdown),
        )
    snap = risk_snapshot(
        item.adj_closes, spy=bench.adj.get(BENCHMARK, []), qqq=bench.adj.get("QQQ", [])
    )
    if snap is None:
        return None
    return TickerRisk(
        as_of=snap.as_of,
        source="read_time",
        sessions=snap.sessions,
        vol_3m=snap.vol_3m,
        vol_1y=snap.vol_1y,
        downside_vol_1y=snap.downside_vol_1y,
        beta_spy=snap.beta_spy,
        beta_qqq=snap.beta_qqq,
        corr_spy=snap.corr_spy,
        max_drawdown_1y=snap.max_drawdown_1y,
        drawdown=snap.drawdown,
    )


def _corr(items: Sequence[NameInputs]) -> DynamicsCorr | None:
    names = [item for item in items if item.adj_closes]
    if len(names) < 2:
        return None
    window = [item.adj_closes[-253:] for item in names]
    matrix: list[list[float | None]] = []
    for left in window:
        row: list[float | None] = []
        for right in window:
            _dates, a, b = align_pair(left, right)
            ra, rb = paired_returns(a, b)
            row.append(pearson(ra, rb))
        matrix.append(row)
    return DynamicsCorr(
        window=min(len(series) for series in window) - 1,
        tickers=[item.instrument.ticker for item in names],
        matrix=matrix,
    )


def _indexed_points(series: Series) -> list[DynamicsPoint]:
    return [DynamicsPoint(date=day, value=value) for day, value in indexed(series)]


def _year_ago(rows: Sequence[Any]) -> Any | None:
    if not rows:
        return None
    anchor = rows[-1].as_of
    lo, hi = YEAR_AGO
    candidates = [row for row in rows[:-1] if lo <= (anchor - row.as_of).days <= hi]
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs((anchor - row.as_of).days - 365))


def _growth(now: float | None, before: float | None) -> float | None:
    if now is None or before is None or before <= 0:
        return None
    return now / before - 1.0


def _ttm_row(row: Any) -> TickerTtmRow:
    return TickerTtmRow(
        as_of=row.as_of,
        revenue=_num(row.revenue),
        ebitda=_num(row.ebitda),
        ebit=_num(getattr(row, "ebit", None)),
        cfo=_num(getattr(row, "cfo", None)),
        capex=_num(getattr(row, "capex", None)),
        fcf=_num(row.fcf),
        net_debt=_num(row.net_debt),
        interest_expense=_num(getattr(row, "interest_expense", None)),
        shares=_num(row.shares),
    )


def _fy_row(row: Any) -> TickerFyRow:
    return TickerFyRow(
        as_of=row.as_of,
        fiscal_year=row.fiscal_year,
        revenue=_num(row.revenue),
        net_income=_num(row.net_income),
        cfo=_num(row.cfo),
        ebit=_num(row.ebit),
        gross_profit=_num(row.gross_profit),
        long_term_debt=_num(row.long_term_debt),
        equity=_num(row.equity),
        shares=_num(row.shares),
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def load_names(
    db: Any, tickers: Sequence[str], *, today: date
) -> tuple[list[NameInputs], list[str]]:
    """Stored inputs for each ticker, in request order. Unknown tickers come back as missing."""
    found = []
    missing: list[str] = []
    for ticker in tickers:
        instrument = instrument_by_ticker(db, ticker)
        if instrument is None:
            missing.append(ticker)
        else:
            found.append(instrument)
    ids = [item.id for item in found]
    start = today - timedelta(days=LOOKBACK_DAYS)
    closes = closes_for_instrument_ids(db, ids, start=start)
    adj = adj_closes_for_instrument_ids(db, ids, start=start)
    ttm = metric_ttm_history(db, ids)
    fy = metric_fy_history(db, ids)
    values = latest_valuation_map(db, ids)
    scores, ranked = opportunity_score_map(db, ids)
    risk = latest_risk_stats(db, ids)
    items = [
        NameInputs(
            instrument=inst,
            universes=universes_for_instrument(db, inst.id),
            closes=_floats(closes.get(inst.id, [])),
            adj_closes=_floats(adj.get(inst.id, [])),
            ttm=ttm.get(inst.id, []),
            fy=fy.get(inst.id, []),
            valuation=values.get(inst.id),
            score=scores.get(inst.id),
            ranked=ranked,
            risk=risk.get(inst.id),
            events=upcoming_events_for_ticker(db, inst.ticker, start=today),
            news=news_for_name(db, inst.ticker, _name_hint(inst.name)),
        )
        for inst in found
    ]
    return items, missing


def load_benchmarks(db: Any, *, today: date) -> Benchmarks:
    catalog = load_universes()
    sector_etf = {
        item.sector: item.ticker
        for item in catalog.tape.instruments
        if item.role == "sector" and item.sector
    }
    wanted = [BENCHMARK, "QQQ", *sector_etf.values()]
    found = {item.ticker: item.id for t in wanted if (item := instrument_by_ticker(db, t))}
    adj = adj_closes_for_instrument_ids(
        db, list(found.values()), start=today - timedelta(days=LOOKBACK_DAYS)
    )
    return Benchmarks(
        adj={
            ticker: _floats(adj.get(instrument_id, [])) for ticker, instrument_id in found.items()
        },
        sector_etf=sector_etf,
    )


def _floats(rows: Sequence[tuple[date, Any]]) -> Series:
    return [(day, float(value)) for day, value in rows if value is not None]


def _name_hint(name: str | None) -> str | None:
    """First word of the company name when it is distinctive enough to match headlines."""
    if not name:
        return None
    word = name.split()[0].strip(",.").removesuffix("'s")
    return word if len(word) >= 5 else None
