from datetime import date

from pytest import approx

from analytics.returns import momentum_return
from analytics.scores import (
    GateInput,
    ScoreGate,
    ScoreInput,
    score_universe,
    sector_ranks,
    unit_ranks,
)


def test_unit_ranks_are_zero_to_one() -> None:
    ranks = unit_ranks([1.0, 2.0, 3.0, None])
    assert ranks[0] == approx(1 / 3)
    assert ranks[1] == approx(2 / 3)
    assert ranks[2] == 1.0
    assert ranks[3] is None


def test_cheapest_quality_grower_ranks_first_and_trap_is_penalized() -> None:
    rows = [
        ScoreInput(
            ticker="TRAP",
            pctile_5y=5.0,
            ebitda_growth_1y=-0.4,
            fcf_margin=0.02,
            net_debt_to_ebitda=9.0,
            momentum=-0.2,
        ),
        ScoreInput(
            ticker="GEM",
            pctile_5y=10.0,
            ebitda_growth_1y=0.25,
            fcf_margin=0.20,
            net_debt_to_ebitda=-1.0,
            momentum=0.08,
        ),
        ScoreInput(
            ticker="RICH",
            pctile_5y=90.0,
            ebitda_growth_1y=0.05,
            fcf_margin=0.10,
            net_debt_to_ebitda=1.0,
            momentum=0.02,
        ),
    ]
    scored = score_universe(rows)
    assert [item.ticker for item in scored] == ["GEM", "RICH", "TRAP"]
    gem = scored[0]
    assert gem.rank == 1
    assert gem.trap is False
    assert gem.insider == 0.5
    assert gem.cheap > 0.8
    trap = next(item for item in scored if item.ticker == "TRAP")
    assert trap.trap is True
    assert trap.risk > gem.risk
    assert trap.total < gem.total


def test_quality_blends_fcf_yield_when_present() -> None:
    same = dict(
        pctile_5y=50.0,
        ebitda_growth_1y=0.1,
        fcf_margin=0.10,
        net_debt_to_ebitda=1.0,
        momentum=0.0,
    )
    scored = score_universe(
        [
            ScoreInput(ticker="CASH", fcf_yield=0.08, **same),
            ScoreInput(ticker="THIN", fcf_yield=0.01, **same),
        ]
    )
    by_ticker = {item.ticker: item for item in scored}
    assert by_ticker["CASH"].quality > by_ticker["THIN"].quality


def _gate(**overrides: object) -> GateInput:
    base: dict[str, object] = dict(
        ticker="X",
        ttm_as_of=date(2026, 9, 30),
        revenue=1_000.0,
        fcf=80.0,
        prior_fcf_low=60.0,
        fcf_yield=0.06,
        ebitda_growth_1y=0.2,
        ev_ebitda=12.0,
    )
    base.update(overrides)
    return GateInput(**base)  # type: ignore[arg-type]


def _rules(row: GateInput) -> list[str]:
    return [item.rule for item in ScoreGate(date(2026, 11, 6)).check(row)]


def test_clean_name_passes_the_gate() -> None:
    assert _rules(_gate()) == []


def test_fcf_flip_within_a_year_is_a_one_off() -> None:
    # KODK: FCF TTM −50M → 465M on 1.1B revenue, three quarters later still in the TTM.
    found = ScoreGate(date(2026, 11, 6)).check(
        _gate(revenue=1_142.0, fcf=465.0, prior_fcf_low=-50.0, fcf_yield=0.25)
    )
    assert [item.rule for item in found] == ["fcf_one_off"]
    assert found[0].values == {"fcf_from": -50.0, "fcf_to": 465.0}
    # A small flip is ordinary noise, not a one-off.
    assert _rules(_gate(fcf=40.0, prior_fcf_low=-20.0)) == []


def test_fcf_yield_above_thirty_percent_is_a_one_off() -> None:
    assert _rules(_gate(fcf_yield=0.64)) == ["fcf_one_off"]


def test_base_effect_extreme_multiple_and_stale_ttm() -> None:
    assert _rules(_gate(ebitda_growth_1y=8.64)) == ["base_effect"]
    assert _rules(_gate(ebitda_growth_1y=-3.5)) == ["base_effect"]
    assert _rules(_gate(ev_ebitda=174.0)) == ["extreme_multiple"]
    assert _rules(_gate(ttm_as_of=date(2026, 4, 26))) == ["stale_ttm"]
    assert _rules(_gate(ttm_as_of=date(2026, 6, 9))) == []


def test_sector_ranks_compare_within_the_sector() -> None:
    sectors = ["Tech"] * 10 + ["Energy"] * 10
    values = [float(item) for item in range(10, 20)] + [float(item) for item in range(10)]
    ranks = sector_ranks(values, sectors)
    # The best energy name ranks first in its sector although every tech name beats it.
    assert ranks[19] == 1.0
    assert ranks[9] == 1.0
    assert unit_ranks(values)[19] == approx(0.5)


def test_small_and_unknown_sectors_are_ranked_together() -> None:
    sectors = ["Tech"] * 10 + ["Utilities", "Utilities", None]
    values = [float(item) for item in range(10)] + [100.0, 50.0, 75.0]
    ranks = sector_ranks(values, sectors)
    assert ranks[10] == 1.0
    assert ranks[11] == approx(1 / 3)
    assert ranks[12] == approx(2 / 3)


def test_momentum_skips_the_last_month() -> None:
    closes = [100.0] * 231 + [150.0] * 21 + [90.0]
    assert len(closes) == 253
    # 12-1: from 253 sessions ago to 21 sessions ago, ignoring the last-month drop.
    assert momentum_return(closes) == approx(50.0)
    assert momentum_return(closes[1:]) is None
