from datetime import date, timedelta

import pytest

from analytics.returns import index_to_100, period_return
from analytics.rrg import (
    iso_week_end_indices,
    jdk_normalize,
    rrg_series,
    select_trail,
    sma,
)
from store.catalog import load_universes


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_sma_and_jdk_identity_at_one_hundred() -> None:
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    constant = [10.0] * 8
    ratio = jdk_normalize(constant, 4)
    assert ratio[:3] == [None, None, None]
    assert all(value == 100.0 for value in ratio[3:])


def test_constant_relative_strength_sits_at_origin() -> None:
    n = 100
    spy = [100.0] * n
    px = [50.0] * n
    last = rrg_series(_dates(n), px, spy)[-1]
    assert last.rs_ratio == 100.0
    assert last.rs_momentum == 100.0
    assert last.quadrant == "leading"


def test_outperformer_then_giveback_moves_leading_to_weakening() -> None:
    n_up, extra = 50, 8
    n = n_up + extra
    spy = [100.0] * n
    px: list[float] = []
    price = 100.0
    for i in range(n):
        price *= 1.008 if i < n_up else 0.999
        px.append(price)
    dates = _dates(n)
    at_peak = rrg_series(dates[:n_up], px[:n_up], spy[:n_up], ratio_window=20, mom_window=5)
    after = rrg_series(dates, px, spy, ratio_window=20, mom_window=5)
    assert at_peak[-1].quadrant == "leading"
    assert after[-1].quadrant == "weakening"
    assert after[-1].as_of > at_peak[-1].as_of


def test_period_return_and_index_to_100() -> None:
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0]
    assert period_return(closes, 5) == pytest.approx(10.0)
    assert period_return(closes, 6) is None
    dates = _dates(2)
    indexed = index_to_100(dates, [80.0, 88.0], window=2)
    assert indexed == [(dates[0], 100.0), (dates[1], 110.0)]


def test_iso_week_ends_and_trail_appends_latest() -> None:
    dates = _dates(10, start=date(2024, 1, 1))  # Mon 1 Jan … Wed 10 Jan
    ends = iso_week_end_indices(dates)
    assert dates[ends[0]] == date(2024, 1, 7)
    n = 90
    long_dates = _dates(n)
    series = rrg_series(
        long_dates,
        [100.0 + i * 0.1 for i in range(n)],
        [100.0] * n,
        ratio_window=5,
        mom_window=3,
    )
    trail = select_trail(series, weeks=3)
    assert trail[-1].as_of == series[-1].as_of
    assert 3 <= len(trail) <= 4


def test_tape_rrg_universe_is_sectors_and_groups() -> None:
    catalog = load_universes()
    roles = set(catalog.live.mover_roles)
    members = [item for item in catalog.tape.instruments if item.role in roles]
    tickers = {item.ticker for item in members}
    assert roles == {"sector", "group"}
    assert len(members) == 13
    assert tickers >= {"XLK", "XLF", "XLV", "XLY", "XLP", "XLI", "XLE", "XLB", "XLU", "XLRE", "XLC"}
    assert {"SMH", "IGV"} <= tickers
    assert tickers.isdisjoint({"SPY", "HYG", "LQD", "UUP", "^VIX", "TLT"})
    assert any(
        item.ticker == "SPY" and item.role == "benchmark" for item in catalog.tape.instruments
    )
