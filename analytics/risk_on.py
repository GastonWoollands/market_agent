"""Risk-On v1 (−1…+1) from stored tape bars + FRED observations.

Polymarket odds are displayed elsewhere and are not an input.

Weights (sum to 1.0):
  inv_vix  0.20  −z(VIXCLS)              higher vol → risk-off
  hyg_lqd  0.20   z(HYG / LQD)           high-yield vs investment-grade
  rsp_spy  0.20   z(RSP / SPY)           equal-weight breadth
  curve    0.20   z(T10Y2Y)              2s10s, not inverted
  cyc_def  0.20   z(cyclicals / defs)    XLY+XLI+XLF+XLK vs XLP+XLU+XLV

Each factor is a trailing z-score over WINDOW observations (min MIN_OBS),
clipped to [-2, 2]. The weighted mean is clipped to [-1, 1]. Missing
factors are dropped and remaining weights are renormalized. Fewer than
MIN_FACTORS inputs → score is None.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import fmean, pstdev

WEIGHTS: dict[str, float] = {
    "inv_vix": 0.20,
    "hyg_lqd": 0.20,
    "rsp_spy": 0.20,
    "curve": 0.20,
    "cyc_def": 0.20,
}

CYCLICALS = ("XLY", "XLI", "XLF", "XLK")
DEFENSIVES = ("XLP", "XLU", "XLV")
VIX_SERIES = "VIXCLS"
CURVE_SERIES = "T10Y2Y"
RISK_ON_TICKERS = ("HYG", "LQD", "RSP", "SPY") + CYCLICALS + DEFENSIVES
WINDOW = 252
MIN_OBS = 60
MIN_FACTORS = 3
Z_CLIP = 2.0

Series = Sequence[tuple[date, float]]


@dataclass(frozen=True)
class RiskOnResult:
    score: float | None
    as_of: date | None
    stale: bool
    factors: dict[str, float | None]


def _to_map(series: Series) -> dict[date, float]:
    return {day: value for day, value in series}


def _aligned_ratio(left: Series, right: Series) -> list[tuple[date, float]]:
    rhs = _to_map(right)
    out: list[tuple[date, float]] = []
    for day, value in left:
        other = rhs.get(day)
        if other is None or other == 0:
            continue
        out.append((day, value / other))
    return out


def _basket_ratio(
    cyclicals: Mapping[str, Series],
    defensives: Mapping[str, Series],
) -> list[tuple[date, float]]:
    cyc_maps = {name: _to_map(series) for name, series in cyclicals.items()}
    def_maps = {name: _to_map(series) for name, series in defensives.items()}
    dates = set()
    for series in (*cyc_maps.values(), *def_maps.values()):
        dates.update(series)
    out: list[tuple[date, float]] = []
    for day in sorted(dates):
        try:
            cyc_vals = [cyc_maps[name][day] for name in CYCLICALS]
            def_vals = [def_maps[name][day] for name in DEFENSIVES]
        except KeyError:
            continue
        defensive_mean = fmean(def_vals)
        if defensive_mean == 0:
            continue
        out.append((day, fmean(cyc_vals) / defensive_mean))
    return out


def trailing_z(series: Series, *, window: int = WINDOW, min_obs: int = MIN_OBS) -> float | None:
    if not series:
        return None
    values = [item[1] for item in sorted(series, key=lambda item: item[0])[-window:]]
    if len(values) < min_obs:
        return None
    spread = pstdev(values)
    if spread == 0:
        return 0.0
    z = (values[-1] - fmean(values)) / spread
    return max(-Z_CLIP, min(Z_CLIP, z))


def combine_factors(factors: Mapping[str, float | None]) -> float | None:
    usable = [
        (WEIGHTS[name], value)
        for name, value in factors.items()
        if name in WEIGHTS and value is not None
    ]
    if len(usable) < MIN_FACTORS:
        return None
    weight_sum = sum(weight for weight, _ in usable)
    if weight_sum <= 0:
        return None
    score = sum(weight * value for weight, value in usable) / weight_sum
    return max(-1.0, min(1.0, score))


def compute_risk_on(
    *,
    vix: Series,
    hyg: Series,
    lqd: Series,
    rsp: Series,
    spy: Series,
    curve: Series,
    cyclicals: Mapping[str, Series],
    defensives: Mapping[str, Series],
    now: date | None = None,
    stale_after_days: int = 5,
) -> RiskOnResult:
    factors = {
        "inv_vix": _negate(trailing_z(vix)),
        "hyg_lqd": trailing_z(_aligned_ratio(hyg, lqd)),
        "rsp_spy": trailing_z(_aligned_ratio(rsp, spy)),
        "curve": trailing_z(curve),
        "cyc_def": trailing_z(_basket_ratio(cyclicals, defensives)),
    }
    as_of = _latest_date(vix, hyg, lqd, rsp, spy, curve)
    score = combine_factors(factors)
    age_stale = now is not None and as_of is not None and (now - as_of).days > stale_after_days
    return RiskOnResult(
        score=score,
        as_of=as_of,
        stale=score is None or as_of is None or age_stale,
        factors=factors,
    )


def _negate(value: float | None) -> float | None:
    if value is None:
        return None
    return -value


def _latest_date(*series: Series) -> date | None:
    dates = [item[0] for seq in series for item in seq]
    return max(dates) if dates else None
