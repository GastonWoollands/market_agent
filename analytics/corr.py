"""63-session Pearson correlation and lead-lag on stored daily closes.

Stdlib `statistics.correlation` — not pandas/numpy, not a heatmap vendor.
Inputs are equity ETF closes already in Postgres. Credit, vol, FX, and
Polymarket are not in this matrix.

Daily returns are simple percent changes on an inner-joined date index.

Lead-lag lag k is corr(a[t], b[t+k]):
  k > 0  a today vs b in k sessions  → a leads b
  k < 0  a today vs b k sessions ago → b leads a
  k = 0  same-day

The usual peak is lag 0. Report that so later briefs cannot invent leadership.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from statistics import StatisticsError, correlation

from analytics.returns import LOOKBACK_3M
from analytics.rrg import align_pair

CORR_WINDOW = LOOKBACK_3M
LAG_MIN = -5
LAG_MAX = 5
MIN_OBS = 40
DEFAULT_LEAD = "XLK"
DEFAULT_LAG = "XLF"

Series = Sequence[tuple[date, float]]


def daily_returns(closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for prior, value in zip(closes[:-1], closes[1:], strict=True):
        if prior == 0:
            continue
        out.append(value / prior - 1.0)
    return out


def paired_returns(
    left: Sequence[float], right: Sequence[float]
) -> tuple[list[float], list[float]]:
    a_out: list[float] = []
    b_out: list[float] = []
    for prior_a, next_a, prior_b, next_b in zip(
        left[:-1], left[1:], right[:-1], right[1:], strict=True
    ):
        if prior_a == 0 or prior_b == 0:
            continue
        a_out.append(next_a / prior_a - 1.0)
        b_out.append(next_b / prior_b - 1.0)
    return a_out, b_out


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    try:
        return correlation(left, right)
    except StatisticsError:
        return None


def aligned_returns(
    left: Series,
    right: Series,
    *,
    window: int = CORR_WINDOW,
    extra: int = 0,
) -> tuple[list[float], list[float]]:
    _dates, a, b = align_pair(left, right)
    need = window + extra + 1
    if len(a) < MIN_OBS + 1:
        return [], []
    if len(a) > need:
        a = a[-need:]
        b = b[-need:]
    ra, rb = paired_returns(a, b)
    if len(ra) < MIN_OBS:
        return [], []
    return ra, rb


def corr_matrix(
    series: Mapping[str, Series],
    tickers: Sequence[str],
    *,
    window: int = CORR_WINDOW,
) -> list[list[float | None]]:
    n = len(tickers)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]
    for i, left_name in enumerate(tickers):
        for j, right_name in enumerate(tickers):
            if j < i:
                matrix[i][j] = matrix[j][i]
                continue
            left, right = aligned_returns(
                series.get(left_name, []),
                series.get(right_name, []),
                window=window,
            )
            if len(left) < MIN_OBS:
                continue
            matrix[i][j] = pearson(left, right)
    return matrix


def cross_corr_at_lag(left: Sequence[float], right: Sequence[float], lag: int) -> float | None:
    if lag == 0:
        return pearson(left, right)
    if lag > 0:
        if len(left) <= lag:
            return None
        return pearson(left[:-lag], right[lag:])
    shift = -lag
    if len(left) <= shift:
        return None
    return pearson(left[shift:], right[:-shift])


def lead_lag(
    left: Series,
    right: Series,
    *,
    window: int = CORR_WINDOW,
    lag_min: int = LAG_MIN,
    lag_max: int = LAG_MAX,
) -> list[tuple[int, float | None]]:
    extra = max(abs(lag_min), abs(lag_max))
    a, b = aligned_returns(left, right, window=window, extra=extra)
    if len(a) < MIN_OBS:
        return [(lag, None) for lag in range(lag_min, lag_max + 1)]
    return [(lag, cross_corr_at_lag(a, b, lag)) for lag in range(lag_min, lag_max + 1)]


def peak_lag(bars: Sequence[tuple[int, float | None]]) -> int | None:
    valid = [(lag, corr) for lag, corr in bars if corr is not None]
    if not valid:
        return None
    lag, _corr = max(valid, key=lambda item: (abs(item[1]), -abs(item[0])))
    return lag


def lead_lag_note(left: str, right: str, lag: int | None) -> str:
    if lag is None:
        return "Lead-lag unavailable (not enough overlapping daily bars)."
    if lag == 0:
        return (
            "Peak |corr| at lag 0 (same-day). This is the usual finding — "
            "not identified leadership."
        )
    sessions = abs(lag)
    unit = "session" if sessions == 1 else "sessions"
    if lag > 0:
        return (
            f"Peak |corr| at lag {lag:+d} ({left} leads {right} by {sessions} {unit}). "
            "Not a trading signal."
        )
    return (
        f"Peak |corr| at lag {lag:+d} ({right} leads {left} by {sessions} {unit}). "
        "Not a trading signal."
    )
