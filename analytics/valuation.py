"""EV/EBITDA from stored closes + TTM facts. No vendor calls.

EV_t = close_t × shares(as of last 10-Q on or before t) + net_debt
multiple_t = EV_t / EBITDA_t when EBITDA > 0 and EV > 0

5y percentile is the rank of today's multiple in that name's own daily series.
1y decomposition: EBITDA growth × multiple change (re-rating).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

MIN_COMPARABLE_OBS = 252
LOOKBACK_DAYS = 5 * 365 + 30
YEAR_DAYS = 365


@dataclass(frozen=True)
class Fundamental:
    as_of: date
    ebitda: float
    net_debt: float
    shares: float


@dataclass(frozen=True)
class ValuationSnapshot:
    as_of: date
    ev: float
    ebitda: float
    ev_ebitda: float
    pctile_5y: float | None
    ebitda_growth_1y: float | None
    multiple_change_1y: float | None
    comparable: bool
    sample_size: int


def enterprise_value(price: float, shares: float, net_debt: float) -> float:
    return price * shares + net_debt


def ev_to_ebitda(ev: float, ebitda: float) -> float | None:
    if ebitda <= 0 or ev <= 0:
        return None
    return ev / ebitda


def percentile_rank(sample: Sequence[float], value: float) -> float:
    if not sample:
        raise ValueError("sample is empty")
    return 100.0 * sum(1 for item in sample if item <= value) / len(sample)


def pick_fundamental(rows: Sequence[Fundamental], day: date) -> Fundamental | None:
    chosen: Fundamental | None = None
    for row in rows:
        if row.as_of <= day:
            chosen = row
        else:
            break
    return chosen


def multiple_path(
    closes: Sequence[tuple[date, float]],
    fundamentals: Sequence[Fundamental],
) -> list[tuple[date, float, float, float]]:
    ordered = sorted(fundamentals, key=lambda item: item.as_of)
    out: list[tuple[date, float, float, float]] = []
    for day, price in closes:
        if price <= 0:
            continue
        fund = pick_fundamental(ordered, day)
        if fund is None or fund.shares <= 0 or fund.ebitda <= 0:
            continue
        ev = enterprise_value(price, fund.shares, fund.net_debt)
        multiple = ev_to_ebitda(ev, fund.ebitda)
        if multiple is None:
            continue
        out.append((day, multiple, ev, fund.ebitda))
    return out


def snapshot(
    closes: Sequence[tuple[date, float]],
    fundamentals: Sequence[Fundamental],
    *,
    min_obs: int = MIN_COMPARABLE_OBS,
    year_days: int = YEAR_DAYS,
) -> ValuationSnapshot | None:
    series = multiple_path(closes, fundamentals)
    if not series:
        return None
    day, multiple, ev, ebitda = series[-1]
    comparable = len(series) >= min_obs
    pctile = percentile_rank([item[1] for item in series], multiple) if comparable else None
    prior = _on_or_before(series, day - timedelta(days=year_days))
    growth = None
    rerate = None
    if prior is not None:
        _prior_day, prior_multiple, _prior_ev, prior_ebitda = prior
        if prior_ebitda > 0:
            growth = ebitda / prior_ebitda - 1.0
        if prior_multiple > 0:
            rerate = multiple / prior_multiple - 1.0
    return ValuationSnapshot(
        as_of=day,
        ev=ev,
        ebitda=ebitda,
        ev_ebitda=multiple,
        pctile_5y=pctile,
        ebitda_growth_1y=growth,
        multiple_change_1y=rerate,
        comparable=comparable,
        sample_size=len(series),
    )


def _on_or_before(
    series: Sequence[tuple[date, float, float, float]], target: date
) -> tuple[date, float, float, float] | None:
    chosen = None
    for row in series:
        if row[0] <= target:
            chosen = row
        else:
            break
    return chosen
