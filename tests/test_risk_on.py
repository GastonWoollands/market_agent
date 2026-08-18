from datetime import date, timedelta
from decimal import Decimal

from analytics.lookback import chart_window, value_on_or_before, window_deltas
from analytics.risk_on import MIN_OBS, combine_factors, compute_risk_on, trailing_z


def _series(start: date, values: list[float]) -> list[tuple[date, float]]:
    return [(start + timedelta(days=index), value) for index, value in enumerate(values)]


def test_window_deltas_previous_print_and_calendar_lookbacks() -> None:
    points = [
        (date(2025, 8, 14), Decimal("4.00")),
        (date(2026, 7, 14), Decimal("4.10")),
        (date(2026, 8, 7), Decimal("4.20")),
        (date(2026, 8, 13), Decimal("4.22")),
        (date(2026, 8, 14), Decimal("4.25")),
    ]
    d1, w1, m1, y1 = window_deltas(points)
    assert d1 == Decimal("0.03")
    assert w1 == Decimal("0.05")
    assert m1 == Decimal("0.15")
    assert y1 == Decimal("0.25")
    assert value_on_or_before(points, date(2026, 1, 1)) == Decimal("4.00")
    assert [item[0] for item in chart_window(points, days=10)] == [
        date(2026, 8, 7),
        date(2026, 8, 13),
        date(2026, 8, 14),
    ]


def test_trailing_z_and_inverse_vix_direction() -> None:
    quiet = _series(date(2025, 1, 1), [15.0] * MIN_OBS + [12.0])
    spike = _series(date(2025, 1, 1), [15.0] * MIN_OBS + [30.0])
    assert trailing_z(quiet) is not None and trailing_z(quiet) < 0
    assert trailing_z(spike) is not None and trailing_z(spike) > 0
    result = compute_risk_on(
        vix=spike,
        hyg=_series(date(2025, 1, 1), [80.0] * (MIN_OBS + 1)),
        lqd=_series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
        rsp=_series(date(2025, 1, 1), [150.0] * (MIN_OBS + 1)),
        spy=_series(date(2025, 1, 1), [500.0] * (MIN_OBS + 1)),
        curve=_series(date(2025, 1, 1), [0.2] * MIN_OBS + [0.8]),
        cyclicals={
            "XLY": _series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
            "XLI": _series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
            "XLF": _series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
            "XLK": _series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
        },
        defensives={
            "XLP": _series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
            "XLU": _series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
            "XLV": _series(date(2025, 1, 1), [100.0] * (MIN_OBS + 1)),
        },
        now=date(2025, 1, 1) + timedelta(days=MIN_OBS),
    )
    assert result.factors["inv_vix"] is not None and result.factors["inv_vix"] < 0
    assert result.factors["curve"] is not None and result.factors["curve"] > 0
    assert result.score is not None
    assert -1.0 <= result.score <= 1.0


def test_risk_on_requires_three_factors_and_clips() -> None:
    assert combine_factors({"inv_vix": 0.5, "curve": 0.5}) is None
    assert combine_factors({"inv_vix": 2.0, "hyg_lqd": 2.0, "curve": 2.0}) == 1.0
    assert combine_factors({"inv_vix": -2.0, "hyg_lqd": -2.0, "curve": -2.0}) == -1.0
