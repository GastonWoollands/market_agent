"""Single-name technicals on stored daily closes. Stdlib only, like `analytics/corr.py`.

SMAs, RSI and the 52-week range use the unadjusted close (`bar_daily.c`), which is
what the TradingView chart shows. Returns use adjusted closes (`adj_c`) so dividends
do not read as drops; risk (`analytics/risk.py`) uses the same adjusted series.

RSI is Wilder's 14-session RSI: simple average seed, then 1/14 smoothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

SMA_WINDOWS = (20, 50, 100, 200)
RSI_WINDOW = 14
YEAR = 252
RETURN_WINDOWS = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}

Series = Sequence[tuple[date, float]]


@dataclass(frozen=True)
class Technicals:
    as_of: date
    close: float
    change_1d: float | None
    sma: dict[int, float | None] = field(default_factory=dict)
    vs_sma: dict[int, float | None] = field(default_factory=dict)
    rsi_14: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    vs_high_52w: float | None = None
    returns: dict[str, float | None] = field(default_factory=dict)


def sma(values: Sequence[float], window: int) -> float | None:
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def rsi(values: Sequence[float], window: int = RSI_WINDOW) -> float | None:
    if len(values) <= window:
        return None
    changes = [after - before for before, after in zip(values[:-1], values[1:], strict=True)]
    gain = sum(max(item, 0.0) for item in changes[:window]) / window
    loss = sum(max(-item, 0.0) for item in changes[:window]) / window
    for item in changes[window:]:
        gain = (gain * (window - 1) + max(item, 0.0)) / window
        loss = (loss * (window - 1) + max(-item, 0.0)) / window
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def trailing_return(values: Sequence[float], sessions: int) -> float | None:
    if len(values) <= sessions or values[-1 - sessions] == 0:
        return None
    return values[-1] / values[-1 - sessions] - 1.0


def technicals(closes: Series, adj_closes: Series) -> Technicals | None:
    """Both series ascending by date. `adj_closes` drives returns only."""
    raw = [(day, float(value)) for day, value in closes if value and float(value) > 0]
    if not raw:
        return None
    values = [value for _day, value in raw]
    adjusted = [float(value) for _day, value in adj_closes if value and float(value) > 0]
    last = values[-1]
    year = values[-YEAR:]
    high = max(year)
    sma_values = {window: sma(values, window) for window in SMA_WINDOWS}
    return Technicals(
        as_of=raw[-1][0],
        close=last,
        change_1d=trailing_return(values, 1),
        sma=sma_values,
        vs_sma={
            window: (last / value - 1.0) if value else None
            for window, value in sma_values.items()
        },
        rsi_14=rsi(values),
        high_52w=high,
        low_52w=min(year),
        vs_high_52w=last / high - 1.0 if high > 0 else None,
        returns={
            label: trailing_return(adjusted, sessions)
            for label, sessions in RETURN_WINDOWS.items()
        },
    )


def relative_return(left: float | None, bench: float | None) -> float | None:
    """Excess return over a benchmark for the same window: (1 + a) / (1 + b) − 1."""
    if left is None or bench is None or bench <= -1.0:
        return None
    return (1.0 + left) / (1.0 + bench) - 1.0


def indexed(series: Series, *, sessions: int = YEAR) -> list[tuple[date, float]]:
    """Last `sessions` closes rebased to 100 at the first point."""
    window = [(day, float(value)) for day, value in series if value and float(value) > 0]
    window = window[-(sessions + 1) :]
    if not window:
        return []
    base = window[0][1]
    return [(day, value / base * 100.0) for day, value in window]
