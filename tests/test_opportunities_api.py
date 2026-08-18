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
    )
    tape = build_opportunities(
        [(instrument, score, value, None)],
        as_of=date(2026, 8, 17),
        stale=False,
    )
    assert tape.count == 1
    top = tape.members[0]
    assert top.rank == 1
    assert top.ticker == "GEM"
    assert top.memo is None
    assert top.cheap > top.risk
    assert top.trap is False
    assert top.pctile_5y == 12.0
