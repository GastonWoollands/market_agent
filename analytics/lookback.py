from bisect import bisect_right
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

LOOKBACK_WEEK = 7
LOOKBACK_MONTH = 30
LOOKBACK_YEAR = 365
CHART_DAYS = 365


def sort_points(points: Sequence[tuple[date, Decimal]]) -> list[tuple[date, Decimal]]:
    return sorted(points, key=lambda item: item[0])


def value_on_or_before(
    points: Sequence[tuple[date, Decimal]], target: date
) -> Decimal | None:
    ordered = sort_points(points)
    if not ordered:
        return None
    dates = [item[0] for item in ordered]
    index = bisect_right(dates, target) - 1
    if index < 0:
        return None
    return ordered[index][1]


def window_deltas(
    points: Sequence[tuple[date, Decimal]],
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    """1D is previous print; 1W/1M/1Y are last minus value on or before as_of − N days."""
    ordered = sort_points(points)
    if not ordered:
        return None, None, None, None
    last_date, last = ordered[-1]
    prior = ordered[-2][1] if len(ordered) > 1 else None
    d1 = last - prior if prior is not None else None
    week = value_on_or_before(ordered, last_date - timedelta(days=LOOKBACK_WEEK))
    month = value_on_or_before(ordered, last_date - timedelta(days=LOOKBACK_MONTH))
    year = value_on_or_before(ordered, last_date - timedelta(days=LOOKBACK_YEAR))
    w1 = last - week if week is not None else None
    m1 = last - month if month is not None else None
    y1 = last - year if year is not None else None
    return d1, w1, m1, y1


def chart_window(
    points: Sequence[tuple[date, Decimal]], *, days: int = CHART_DAYS
) -> list[tuple[date, Decimal]]:
    ordered = sort_points(points)
    if not ordered:
        return []
    start = ordered[-1][0] - timedelta(days=days)
    return [item for item in ordered if item[0] >= start]
