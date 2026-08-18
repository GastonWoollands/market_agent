from datetime import date

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
