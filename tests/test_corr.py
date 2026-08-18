from datetime import date, timedelta

import pytest

from analytics.corr import (
    corr_matrix,
    daily_returns,
    lead_lag,
    lead_lag_note,
    peak_lag,
    pearson,
)
from analytics.returns import relative_to_benchmark
from store.catalog import load_universes, tape_with_roles


def _series(values: list[float], start: date = date(2025, 1, 1)) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), value) for i, value in enumerate(values)]


def _prices(returns: list[float], start: float = 100.0) -> list[float]:
    out = [start]
    for value in returns:
        out.append(out[-1] * (1.0 + value))
    return out


def test_relative_tracks_benchmark_at_one_hundred() -> None:
    spy = _series([100.0 + i for i in range(10)])
    twin = _series([50.0 + 0.5 * i for i in range(10)])
    rel = relative_to_benchmark(twin, spy, window=10)
    assert rel[0][1] == 100.0
    assert all(value == pytest.approx(100.0) for _day, value in rel)


def test_relative_outperformer_ends_above_one_hundred() -> None:
    spy = _series([100.0] * 8)
    px = _series([100.0 * (1.01**i) for i in range(8)])
    rel = relative_to_benchmark(px, spy, window=8)
    assert rel[0][1] == 100.0
    assert rel[-1][1] == pytest.approx(100.0 * (1.01**7))


def test_pearson_identity_and_inverse() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert pearson(x, x) == pytest.approx(1.0)
    assert pearson(x, [-v for v in x]) == pytest.approx(-1.0)
    assert pearson(x, [1.0, 1.0, 1.0, 1.0, 1.0]) is None
    assert daily_returns([100.0, 110.0, 121.0]) == pytest.approx([0.1, 0.1])


def test_corr_matrix_symmetric_and_skips_credit() -> None:
    catalog = load_universes()
    sectors = [item.ticker for item in tape_with_roles(catalog, ["sector"])]
    assert len(sectors) == 11
    assert "HYG" not in sectors
    rets = [(i % 5 - 2) * 0.01 for i in range(49)]
    up = _prices(rets)
    down = _prices([-r for r in rets])
    series = {"XLK": _series(up), "XLF": _series(up), "XLU": _series(down)}
    matrix = corr_matrix(series, ["XLK", "XLF", "XLU"], window=40)
    assert matrix[0][1] == pytest.approx(1.0)
    assert matrix[1][0] == matrix[0][1]
    assert matrix[0][2] == pytest.approx(-1.0)
    assert matrix[0][0] == pytest.approx(1.0)


def test_delayed_series_peaks_at_positive_lag() -> None:
    n = 80
    lead_px = [100.0 + i + ((i * i) % 7) * 0.4 for i in range(n)]
    lag_px = [lead_px[0], lead_px[0], *lead_px[:-2]]
    bars = lead_lag(_series(lead_px), _series(lag_px), window=40)
    assert peak_lag(bars) == 2
    assert "leads" in lead_lag_note("XLK", "XLF", 2)
    assert "same-day" in lead_lag_note("XLK", "XLF", 0)
