from datetime import date
from types import SimpleNamespace

from api.opportunities import build_opportunities


def test_rank_one_is_explained_by_sleeves_without_memo() -> None:
    instrument = SimpleNamespace(ticker="GEM", name="Gem Co")
    score = SimpleNamespace(
        rank=1,
        total=0.81,
        cheap=0.88,
        quality=0.76,
        change=0.70,
        setup=0.55,
        insider=0.5,
        risk=0.04,
        trap=False,
        fcf_margin=0.18,
        ret_3m=3.2,
        as_of=date(2026, 8, 17),
    )
    value = SimpleNamespace(
        pctile_5y=12.0,
        ev_ebitda=8.4,
        ebitda_growth_1y=0.22,
        ev=1_000_000_000,
        ebitda=200_000_000,
    )
    instrument.id = 3
    tape = build_opportunities(
        [(instrument, score, value, None)],
        as_of=date(2026, 8, 17),
        stale=False,
        ttm_by_id={3: SimpleNamespace(fcf=80_000_000, net_debt=100_000_000)},
        fy_by_id={3: SimpleNamespace(cfo=10, net_income=12)},
    )
    assert tape.count == 1
    top = tape.members[0]
    assert top.rank == 1
    assert top.ticker == "GEM"
    assert top.memo is None
    assert top.cheap > top.risk
    assert top.trap is False
    assert top.pctile_5y == 12.0
    assert top.fcf_yield == 0.08
    assert top.nd_ebitda == 0.5
    assert top.accrual is False


def test_opportunity_blank_yield_when_ttm_missing() -> None:
    instrument = SimpleNamespace(ticker="GAP", name="Gap Co", id=1)
    score = SimpleNamespace(
        rank=2,
        total=0.4,
        cheap=0.5,
        quality=0.5,
        change=0.5,
        setup=0.5,
        insider=0.5,
        risk=0.0,
        trap=True,
        fcf_margin=None,
        ret_3m=None,
    )
    value = SimpleNamespace(
        pctile_5y=None,
        ev_ebitda=None,
        ebitda_growth_1y=-0.1,
        ev=None,
        ebitda=None,
    )
    tape = build_opportunities(
        [(instrument, score, value, None)],
        as_of=date(2026, 8, 17),
        stale=False,
    )
    row = tape.members[0]
    assert row.fcf_yield is None
    assert row.nd_ebitda is None
    assert row.accrual is None
    assert row.trap is True
