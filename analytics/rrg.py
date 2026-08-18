"""JdK Relative Rotation Graph (RS-Ratio / RS-Momentum) vs a benchmark.

Computed from stored daily closes. Not a StockCharts scrape, not a pandas port,
and not mixed with credit/vol/FX proxies or Polymarket odds.

  RS            = price / SPY
  rs_ratio      = 100 * RS / SMA(RS, 60)          ~12 trading weeks
  rs_momentum   = 100 * rs_ratio / SMA(rs_ratio, 20)   ~4 weeks

Origin is (100, 100). Quadrants (inclusive of the axes):

  Leading    ratio ≥ 100 and momentum ≥ 100
  Weakening  ratio ≥ 100 and momentum < 100
  Lagging    ratio < 100 and momentum < 100
  Improving  ratio < 100 and momentum ≥ 100

Trails are the last TRAIL_WEEKS ISO-week-end points, plus the latest daily
print when it is not already a week-end.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

BENCHMARK = "SPY"
RATIO_WINDOW = 60
MOM_WINDOW = 20
TRAIL_WEEKS = 8
MIN_BARS = RATIO_WINDOW + MOM_WINDOW - 1

QUADRANT_ORDER = ("leading", "weakening", "lagging", "improving")
QUADRANT_LABELS = {
    "leading": "Leading",
    "weakening": "Weakening",
    "lagging": "Lagging",
    "improving": "Improving",
}


@dataclass(frozen=True)
class RrgObservation:
    as_of: date
    rs_ratio: float
    rs_momentum: float
    quadrant: str


def sma(values: Sequence[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        if index >= window - 1:
            out[index] = running / window
    return out


def jdk_normalize(values: Sequence[float], window: int) -> list[float | None]:
    means = sma(values, window)
    return [
        None if mean is None or mean == 0 else 100.0 * value / mean
        for value, mean in zip(values, means, strict=True)
    ]


def quadrant(rs_ratio: float, rs_momentum: float) -> str:
    if rs_ratio >= 100 and rs_momentum >= 100:
        return "leading"
    if rs_ratio >= 100:
        return "weakening"
    if rs_momentum >= 100:
        return "improving"
    return "lagging"


def align_pair(
    left: Sequence[tuple[date, float]],
    right: Sequence[tuple[date, float]],
) -> tuple[list[date], list[float], list[float]]:
    rhs = {day: value for day, value in right}
    dates: list[date] = []
    a: list[float] = []
    b: list[float] = []
    for day, value in left:
        other = rhs.get(day)
        if other is None or other == 0:
            continue
        dates.append(day)
        a.append(float(value))
        b.append(float(other))
    return dates, a, b


def iso_week_end_indices(dates: Sequence[date]) -> list[int]:
    last: dict[tuple[int, int], int] = {}
    for index, day in enumerate(dates):
        iso = day.isocalendar()
        last[(iso.year, iso.week)] = index
    return [last[key] for key in sorted(last)]


def rrg_series(
    dates: Sequence[date],
    price: Sequence[float],
    bench: Sequence[float],
    *,
    ratio_window: int = RATIO_WINDOW,
    mom_window: int = MOM_WINDOW,
) -> list[RrgObservation]:
    if len(dates) != len(price) or len(dates) != len(bench):
        raise ValueError("dates, price, and bench must align")
    if len(dates) < ratio_window + mom_window - 1:
        return []
    rs = [px / bx for px, bx in zip(price, bench, strict=True)]
    ratio = jdk_normalize(rs, ratio_window)
    first = next((i for i, value in enumerate(ratio) if value is not None), None)
    if first is None:
        return []
    dense = [value for value in ratio[first:] if value is not None]
    momentum = jdk_normalize(dense, mom_window)
    out: list[RrgObservation] = []
    for offset, (rs_ratio, rs_mom) in enumerate(zip(dense, momentum, strict=True)):
        if rs_mom is None:
            continue
        out.append(
            RrgObservation(
                as_of=dates[first + offset],
                rs_ratio=rs_ratio,
                rs_momentum=rs_mom,
                quadrant=quadrant(rs_ratio, rs_mom),
            )
        )
    return out


def compute_rrg(
    price: Sequence[tuple[date, float]],
    benchmark: Sequence[tuple[date, float]],
    *,
    ratio_window: int = RATIO_WINDOW,
    mom_window: int = MOM_WINDOW,
) -> list[RrgObservation]:
    dates, px, bx = align_pair(price, benchmark)
    return rrg_series(
        dates,
        px,
        bx,
        ratio_window=ratio_window,
        mom_window=mom_window,
    )


def select_trail(
    series: Sequence[RrgObservation],
    *,
    weeks: int = TRAIL_WEEKS,
) -> list[RrgObservation]:
    if not series:
        return []
    dates = [item.as_of for item in series]
    by_date = {item.as_of: item for item in series}
    ends = [dates[index] for index in iso_week_end_indices(dates)[-weeks:]]
    latest = series[-1].as_of
    if latest not in ends:
        ends.append(latest)
    return [by_date[day] for day in ends]
