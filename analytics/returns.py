"""Equity period returns and rebase-to-100 series from stored closes.

Lookbacks are trading-session counts, not calendar days (unlike FRED level deltas):
  1W  5   1M  21   3M  63   1Y  252
Indexed series rebase the last INDEX_WINDOW closes so the first print is 100.
"""

from collections.abc import Sequence
from datetime import date

LOOKBACK_1W = 5
LOOKBACK_1M = 21
LOOKBACK_3M = 63
LOOKBACK_1Y = 252
INDEX_WINDOW = 63


def period_return(closes: Sequence[float], lookback: int) -> float | None:
    if lookback <= 0 or len(closes) <= lookback:
        return None
    start = closes[-1 - lookback]
    if start == 0:
        return None
    return (closes[-1] / start - 1) * 100.0


def index_to_100(
    dates: Sequence[date],
    closes: Sequence[float],
    *,
    window: int = INDEX_WINDOW,
) -> list[tuple[date, float]]:
    if window <= 0 or len(dates) != len(closes) or not closes:
        return []
    slice_dates = list(dates[-window:])
    slice_closes = list(closes[-window:])
    base = slice_closes[0]
    if base == 0:
        return []
    return [
        (day, 100.0 * close / base)
        for day, close in zip(slice_dates, slice_closes, strict=True)
    ]
