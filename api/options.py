"""Options read for the Ticker page and the market options panel on Dynamics.

Reads `option_stats`, `option_chain_snapshot` (IVs solved by the job), the vol indices on
the tape and Cboe `options_market_stats`. Nothing is fetched here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from analytics.options import expiry_read, iv_rank
from api.schemas import (
    MarketOptionsResponse,
    OptionSmilePoint,
    OptionTermPoint,
    PutCallLatest,
    PutCallPoint,
    TickerOptions,
    VixRatioPoint,
    VixTermPoint,
    VolIndexRow,
)
from store.repos import (
    closes_for_tickers,
    latest_option_stats,
    option_chain_rows,
    option_iv_history,
    options_market_history,
)

OUT_OF_SCOPE = (
    "Not in the options scope (watchlist, Opportunities top 25, SPY / QQQ / IWM, sector ETFs)."
)
SMILE_DTE = 30
YEAR_SESSIONS = 252
LOOKBACK_DAYS = 400
# (ticker, label, days to expiry) on the VIX term structure.
VIX_CURVE = (("^VIX9D", "9d", 9), ("^VIX", "30d", 30), ("^VIX3M", "3m", 93))
VOL_INDICES = (("^VIX", "VIX"), ("^VVIX", "VVIX"), ("^SKEW", "SKEW"))
PUT_CALL = (
    ("equity", "Equity"),
    ("index", "Index"),
    ("spx", "SPX + SPXW"),
    ("total", "Total"),
    ("vix", "VIX options"),
)


def build_ticker_options(
    stats: Any | None, chain: Sequence[Any], history: Sequence[float]
) -> TickerOptions:
    if stats is None:
        return TickerOptions(unavailable=OUT_OF_SCOPE)
    spot = float(stats.spot)
    by_expiry: dict[date, list[tuple[str, float, float]]] = {}
    for row in chain:
        if row.iv is not None:
            by_expiry.setdefault(row.expiry, []).append(
                (row.kind, float(row.strike), float(row.iv))
            )
    reads = [
        expiry_read(expiry, stats.as_of, spot, points)
        for expiry, points in sorted(by_expiry.items())
    ]
    term = [
        OptionTermPoint(expiry=read.expiry, dte=read.dte, atm_iv=read.atm_iv)
        for read in reads
        if read.atm_iv is not None
    ]
    smile_read = min(reads, key=lambda read: abs(read.dte - SMILE_DTE), default=None)
    atm = _opt(stats.atm_iv_30d)
    return TickerOptions(
        as_of=stats.as_of,
        spot=spot,
        atm_iv_30d=atm,
        atm_iv_90d=_opt(stats.atm_iv_90d),
        term_slope=_opt(stats.term_slope),
        skew_30d=_opt(stats.skew_30d),
        rv_1y=_opt(stats.rv_1y),
        iv_rv=_opt(stats.iv_rv),
        iv_rank=None if atm is None else iv_rank(history, atm),
        iv_sessions=len(history),
        pc_volume=_opt(stats.pc_volume),
        pc_oi=_opt(stats.pc_oi),
        call_volume=stats.call_volume,
        put_volume=stats.put_volume,
        earnings_date=stats.earnings_date,
        earnings_estimate=stats.earnings_estimate,
        move_expiry=stats.move_expiry,
        expected_move=_opt(stats.expected_move),
        term=term,
        smile_expiry=smile_read.expiry if smile_read else None,
        smile=[
            OptionSmilePoint(moneyness=moneyness, iv=iv, kind=kind)
            for moneyness, iv, kind in (smile_read.smile if smile_read else ())
        ],
    )


def load_ticker_options(db: Any, instrument_id: int) -> TickerOptions:
    stats = latest_option_stats(db, instrument_id)
    if stats is None:
        return build_ticker_options(None, [], [])
    chain = option_chain_rows(db, instrument_id, stats.as_of)
    history = [float(value) for value in option_iv_history(db, instrument_id, before=stats.as_of)]
    return build_ticker_options(stats, chain, history)


def build_market_options(
    closes: dict[str, list[tuple[date, Any]]], cboe: Sequence[Any]
) -> MarketOptionsResponse:
    series = {
        ticker: [(day, float(value)) for day, value in rows] for ticker, rows in closes.items()
    }
    latest = {ticker: rows[-1][1] for ticker, rows in series.items() if rows}
    curve = [
        VixTermPoint(ticker=ticker, label=label, days=days, value=latest.get(ticker))
        for ticker, label, days in VIX_CURVE
    ]
    front = dict(series.get("^VIX", []))
    ratios = [
        VixRatioPoint(date=day, ratio=front[day] / value)
        for day, value in series.get("^VIX3M", [])
        if day in front and value > 0
    ][-YEAR_SESSIONS:]
    indices = []
    for ticker, label in VOL_INDICES:
        rows = series.get(ticker, [])
        values = [value for _day, value in rows][-YEAR_SESSIONS:]
        indices.append(
            VolIndexRow(
                ticker=ticker,
                label=label,
                value=values[-1] if values else None,
                change_1d=values[-1] - values[-2] if len(values) > 1 else None,
                pct_1y=_percentile(values),
            )
        )

    by_day: dict[date, dict[str, float | None]] = {}
    for row in cboe:
        by_day.setdefault(row.as_of, {})[row.product] = _opt(row.pc_ratio)
    days = sorted(by_day)[-YEAR_SESSIONS:]
    equity = [by_day[day].get("equity") for day in days]
    history = [
        PutCallPoint(
            date=day,
            equity=by_day[day].get("equity"),
            index=by_day[day].get("index"),
            total=by_day[day].get("total"),
            spx=by_day[day].get("spx"),
            equity_10d=_mean(equity[max(index - 9, 0) : index + 1]) if index >= 9 else None,
        )
        for index, day in enumerate(days)
    ]
    latest_pc = []
    for product, label in PUT_CALL:
        values = [by_day[day].get(product) for day in days]
        present = [value for value in values if value is not None]
        latest_pc.append(
            PutCallLatest(
                product=product,
                label=label,
                ratio=values[-1] if values else None,
                pct_1y=_percentile(present) if values and values[-1] is not None else None,
            )
        )
    as_of_points = [rows[-1][0] for rows in series.values() if rows]
    return MarketOptionsResponse(
        as_of=max(as_of_points) if as_of_points else None,
        vix_curve=curve,
        vix_ratio=ratios[-1].ratio if ratios else None,
        vix_ratio_history=ratios,
        indices=indices,
        put_call_as_of=days[-1] if days else None,
        put_call=latest_pc,
        put_call_history=history,
    )


def load_market_options(db: Any, *, today: date) -> MarketOptionsResponse:
    start = today - timedelta(days=LOOKBACK_DAYS)
    tickers = sorted({ticker for ticker, *_rest in VIX_CURVE} | {t for t, _l in VOL_INDICES})
    return build_market_options(
        closes_for_tickers(db, tickers, start=start),
        options_market_history(db, start=start),
    )


def _percentile(values: Sequence[float]) -> float | None:
    """Share of the window at or below the last value; None under half a year of data."""
    if len(values) < YEAR_SESSIONS // 2:
        return None
    today = values[-1]
    return sum(1 for value in values if value <= today) / len(values)


def _mean(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _opt(value: Any) -> float | None:
    return None if value is None else float(value)
