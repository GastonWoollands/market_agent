from datetime import date, timedelta
from math import isclose

from analytics.technicals import indexed, relative_return, rsi, sma, technicals, trailing_return


def _series(values: list[float]) -> list[tuple[date, float]]:
    start = date(2025, 1, 1)
    return [(start + timedelta(days=index), value) for index, value in enumerate(values)]


def test_rsi_extremes_and_balance() -> None:
    assert rsi([float(item) for item in range(1, 40)]) == 100.0
    assert rsi([float(40 - item) for item in range(40)]) == 0.0
    alternating = [100.0 + (1.0 if index % 2 else 0.0) for index in range(60)]
    assert isclose(rsi(alternating), 50.0, abs_tol=2.0)
    assert rsi([1.0] * 10) is None


def test_sma_and_trailing_return() -> None:
    assert sma([1.0, 2.0, 3.0, 4.0], 2) == 3.5
    assert sma([1.0], 2) is None
    assert isclose(trailing_return([100.0, 110.0, 121.0], 2), 0.21)
    assert trailing_return([100.0], 1) is None


def test_technicals_snapshot_on_a_rising_line() -> None:
    values = [100.0 + index for index in range(260)]
    snap = technicals(_series(values), _series(values))
    assert snap is not None
    assert snap.close == 359.0
    assert snap.sma[20] == sum(values[-20:]) / 20
    assert snap.vs_sma[200] > 0
    assert snap.rsi_14 == 100.0
    assert snap.high_52w == 359.0
    assert snap.vs_high_52w == 0.0
    assert snap.low_52w == values[-252]
    assert isclose(snap.returns["1w"], 359.0 / 354.0 - 1)
    assert snap.returns["1y"] is not None


def test_short_history_blanks_long_windows() -> None:
    snap = technicals(_series([10.0, 11.0, 12.0]), _series([10.0, 11.0, 12.0]))
    assert snap is not None
    assert snap.sma[200] is None
    assert snap.vs_sma[200] is None
    assert snap.rsi_14 is None
    assert snap.returns["1m"] is None


def test_relative_return_and_indexed() -> None:
    assert isclose(relative_return(0.10, 0.05), 1.10 / 1.05 - 1)
    assert relative_return(None, 0.05) is None
    points = indexed(_series([50.0, 55.0, 60.0]), sessions=1)
    assert [value for _day, value in points] == [100.0, 60.0 / 55.0 * 100.0]
