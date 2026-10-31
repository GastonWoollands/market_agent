from datetime import date, timedelta
from math import isclose

from analytics.risk import downside_vol, max_drawdown, realized_vol, snapshot


def _series(values: list[float], start: date = date(2025, 1, 1)) -> list[tuple[date, float]]:
    return [(start + timedelta(days=index), value) for index, value in enumerate(values)]


def _path(n: int, step: float, *, base: float = 100.0) -> list[float]:
    out = [base]
    for index in range(1, n):
        out.append(out[-1] * (1 + (step if index % 2 else -step / 2)))
    return out


def test_max_drawdown_is_worst_peak_to_trough() -> None:
    assert isclose(max_drawdown([100, 120, 60, 90, 130, 117]), -0.5)
    assert max_drawdown([1, 2, 3]) == 0.0
    assert max_drawdown([5]) is None


def test_vol_needs_enough_observations() -> None:
    assert realized_vol([0.01] * 10, min_obs=40) is None
    assert realized_vol([0.01, -0.01] * 30, min_obs=40) > 0
    assert downside_vol([0.01] * 60, min_obs=40) == 0.0
    assert downside_vol([0.01, -0.02] * 30, min_obs=40) > 0


def test_beta_of_a_leveraged_copy_is_its_leverage() -> None:
    bench = _path(260, 0.01)
    lever = [100.0]
    for prior, value in zip(bench[:-1], bench[1:], strict=True):
        lever.append(lever[-1] * (1 + 2 * (value / prior - 1)))
    spy = _series(bench)
    risk = snapshot(_series(lever), spy=spy, qqq=spy)
    assert risk is not None
    assert risk.sessions == 252
    assert isclose(risk.beta_spy, 2.0, rel_tol=1e-9)
    assert isclose(risk.corr_spy, 1.0, rel_tol=1e-9)
    assert risk.vol_1y > risk.vol_3m * 0.5
    assert risk.max_drawdown_1y <= 0
    assert risk.drawdown <= 0


def test_short_history_blanks_year_metrics() -> None:
    spy = _series(_path(260, 0.01))
    young = _series(_path(60, 0.03), start=date(2025, 7, 1))
    risk = snapshot(young, spy=spy, qqq=spy)
    assert risk is not None
    assert risk.vol_3m is not None
    assert risk.vol_1y is None
    assert risk.beta_spy is None
    assert risk.max_drawdown_1y is None
    assert risk.drawdown is not None
