from datetime import date, timedelta

import pytest

from api.dynamics import StoredMember, build_dynamics
from store.catalog import load_universes


def test_build_dynamics_drops_credit_and_groups_quadrants() -> None:
    catalog = load_universes()
    stored = [
        StoredMember(
            ticker="XLK",
            name="Information Technology",
            sector="Information Technology",
            as_of=date(2026, 8, 14),
            rs_ratio=102.1,
            rs_momentum=101.4,
            quadrant="leading",
            trail=[(date(2026, 8, 7), 101.0, 102.0), (date(2026, 8, 14), 102.1, 101.4)],
            ret_1w=1.25,
            indexed=[(date(2026, 5, 15), 100.0), (date(2026, 8, 14), 108.0)],
        ),
        StoredMember(
            ticker="HYG",
            name="High Yield",
            sector=None,
            as_of=date(2026, 8, 14),
            rs_ratio=99.0,
            rs_momentum=99.0,
            quadrant="lagging",
            trail=[],
        ),
        StoredMember(
            ticker="XLU",
            name="Utilities",
            sector="Utilities",
            as_of=date(2026, 8, 14),
            rs_ratio=97.2,
            rs_momentum=101.1,
            quadrant="improving",
            trail=[],
        ),
    ]
    payload = build_dynamics(stored, catalog, now=date(2026, 8, 14))
    assert [item.ticker for item in payload.members] == ["XLK", "XLU"]
    assert payload.members[0].role == "sector"
    assert payload.members[0].trail[0].rs_ratio == 101.0
    assert payload.members[0].indexed[-1].value == 108.0
    assert payload.benchmark == "SPY"
    assert payload.stale is False
    assert payload.as_of == date(2026, 8, 14)


def test_build_dynamics_empty_is_stale() -> None:
    payload = build_dynamics([], load_universes(), now=date(2026, 8, 18))
    assert payload.members == []
    assert payload.stale is True
    assert payload.as_of is None
    assert payload.overlay == []
    assert payload.corr is None
    assert payload.lead_lag is None


def test_build_dynamics_relative_overlay_and_same_day_lead_lag() -> None:
    catalog = load_universes()
    n = 80
    start = date(2026, 1, 1)
    rets = [0.01 + (i % 5 - 2) * 0.004 for i in range(n - 1)]
    spy_px = [100.0] * n
    xlk_px = [100.0]
    for value in rets:
        xlk_px.append(xlk_px[-1] * (1.0 + value))
    spy = [(start + timedelta(days=i), spy_px[i]) for i in range(n)]
    xlk = [(start + timedelta(days=i), xlk_px[i]) for i in range(n)]
    xlf = list(xlk)
    xlu = [(start + timedelta(days=i), 100.0 * (0.995**i)) for i in range(n)]
    closes = {"SPY": spy, "XLK": xlk, "XLF": xlf, "XLU": xlu}
    payload = build_dynamics(
        [], catalog, now=date(2026, 3, 22), closes=closes, lead="XLK", lag="XLF"
    )
    by_ticker = {item.ticker: item for item in payload.overlay}
    assert "XLK" in by_ticker
    assert by_ticker["XLK"].points[0].value == 100.0
    assert by_ticker["XLK"].points[-1].value > 100.0
    assert payload.corr is not None
    assert "HYG" not in payload.corr.tickers
    assert payload.corr.window == 63
    xlk_i = payload.corr.tickers.index("XLK")
    xlf_i = payload.corr.tickers.index("XLF")
    assert payload.corr.matrix[xlk_i][xlf_i] == pytest.approx(1.0)
    assert payload.lead_lag is not None
    assert payload.lead_lag.left == "XLK"
    assert payload.lead_lag.right == "XLF"
    assert payload.lead_lag.peak_lag == 0
    assert "same-day" in payload.lead_lag.note
