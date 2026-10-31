"""Per-name price risk on stored adjusted closes: vol, downside vol, beta, drawdown.

Stdlib only, like `analytics/corr.py`. Returns are simple daily changes on adjusted
closes (`bar_daily.adj_c`); annualization is √252. Beta and correlation use the
inner-joined dates with the benchmark, so a halted session never pairs with a move.

`max_drawdown_1y` is the worst peak-to-trough over the last 252 sessions;
`drawdown` is today's distance from the 252-session high. Both are ≤ 0.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import sqrt
from statistics import StatisticsError, correlation, covariance, pstdev, variance

from analytics.corr import daily_returns, paired_returns
from analytics.rrg import align_pair

YEAR = 252
QUARTER = 63
MIN_OBS_QUARTER = 40
MIN_OBS_YEAR = 180
ANNUAL = sqrt(YEAR)

Series = Sequence[tuple[date, float]]


@dataclass(frozen=True)
class RiskSnapshot:
    as_of: date
    sessions: int
    vol_3m: float | None
    vol_1y: float | None
    downside_vol_1y: float | None
    beta_spy: float | None
    beta_qqq: float | None
    corr_spy: float | None
    max_drawdown_1y: float | None
    drawdown: float | None


def realized_vol(returns: Sequence[float], *, min_obs: int) -> float | None:
    if len(returns) < min_obs:
        return None
    return pstdev(returns) * ANNUAL


def downside_vol(returns: Sequence[float], *, min_obs: int) -> float | None:
    """Semi-deviation below zero: √(mean(min(r, 0)²)) annualized."""
    if len(returns) < min_obs:
        return None
    return sqrt(sum(min(item, 0.0) ** 2 for item in returns) / len(returns)) * ANNUAL


def beta(left: Sequence[float], bench: Sequence[float], *, min_obs: int) -> float | None:
    if len(left) < min_obs or len(left) != len(bench):
        return None
    try:
        var = variance(bench)
        if var == 0:
            return None
        return covariance(left, bench) / var
    except StatisticsError:
        return None


def max_drawdown(closes: Sequence[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for value in closes:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def snapshot(
    closes: Series,
    *,
    spy: Series,
    qqq: Series,
) -> RiskSnapshot | None:
    """Risk as of the last close. `closes` ascending by date; benchmarks the same."""
    series = [(day, float(value)) for day, value in closes if value and float(value) > 0]
    if len(series) < 2:
        return None
    year = series[-(YEAR + 1) :]
    values = [value for _day, value in year]
    returns = daily_returns(values)
    quarter = returns[-QUARTER:]
    high = max(values)
    return RiskSnapshot(
        as_of=year[-1][0],
        sessions=len(returns),
        vol_3m=realized_vol(quarter, min_obs=MIN_OBS_QUARTER),
        vol_1y=realized_vol(returns, min_obs=MIN_OBS_YEAR),
        downside_vol_1y=downside_vol(returns, min_obs=MIN_OBS_YEAR),
        beta_spy=_beta_vs(year, spy),
        beta_qqq=_beta_vs(year, qqq),
        corr_spy=_corr_vs(year, spy),
        max_drawdown_1y=max_drawdown(values) if len(returns) >= MIN_OBS_YEAR else None,
        drawdown=values[-1] / high - 1.0 if high > 0 else None,
    )


def _pairs(left: Series, bench: Series) -> tuple[list[float], list[float]]:
    _dates, a, b = align_pair(left, bench)
    return paired_returns(a, b)


def _beta_vs(left: Series, bench: Series) -> float | None:
    a, b = _pairs(left, bench)
    return beta(a, b, min_obs=MIN_OBS_YEAR)


def _corr_vs(left: Series, bench: Series) -> float | None:
    a, b = _pairs(left, bench)
    if len(a) < MIN_OBS_YEAR:
        return None
    try:
        return correlation(a, b)
    except StatisticsError:
        return None
