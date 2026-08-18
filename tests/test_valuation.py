from datetime import date, timedelta

import pytest

from analytics.valuation import (
    Fundamental,
    enterprise_value,
    ev_to_ebitda,
    percentile_rank,
    snapshot,
)


def test_ev_and_multiple_skip_non_positive_ebitda() -> None:
    assert enterprise_value(10.0, 100.0, 50.0) == 1050.0
    assert ev_to_ebitda(1050.0, 50.0) == pytest.approx(21.0)
    assert ev_to_ebitda(1050.0, 0.0) is None
    assert ev_to_ebitda(-10.0, 50.0) is None


def test_percentile_rank_is_share_at_or_below() -> None:
    sample = [10.0, 20.0, 30.0, 40.0]
    assert percentile_rank(sample, 10.0) == 25.0
    assert percentile_rank(sample, 25.0) == 50.0
    assert percentile_rank(sample, 40.0) == 100.0


def test_snapshot_marks_comparable_and_decomposes_growth_times_rerate() -> None:
    start = date(2024, 1, 1)
    closes = [(start + timedelta(days=i), 10.0 + i * 0.01) for i in range(300)]
    funds = [
        Fundamental(as_of=start, ebitda=100.0, net_debt=0.0, shares=10.0),
        Fundamental(as_of=start + timedelta(days=200), ebitda=120.0, net_debt=0.0, shares=10.0),
    ]
    row = snapshot(closes, funds, min_obs=252, year_days=365)
    assert row is not None
    assert row.comparable is True
    assert row.sample_size == 300
    assert row.pctile_5y is not None
    assert row.ebitda_growth_1y is None
    later = snapshot(closes, funds, min_obs=252, year_days=150)
    assert later is not None
    assert later.ebitda_growth_1y == pytest.approx(0.2)
    assert later.multiple_change_1y is not None


def test_short_history_is_not_comparable() -> None:
    start = date(2025, 1, 1)
    closes = [(start + timedelta(days=i), 20.0) for i in range(40)]
    funds = [Fundamental(as_of=start, ebitda=50.0, net_debt=0.0, shares=5.0)]
    row = snapshot(closes, funds, min_obs=252)
    assert row is not None
    assert row.comparable is False
    assert row.pctile_5y is None
    assert row.ev_ebitda == pytest.approx(2.0)
