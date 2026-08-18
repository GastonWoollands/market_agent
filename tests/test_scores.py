from pytest import approx

from analytics.scores import ScoreInput, score_universe, unit_ranks


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
            ret_3m=-0.2,
        ),
        ScoreInput(
            ticker="GEM",
            pctile_5y=10.0,
            ebitda_growth_1y=0.25,
            fcf_margin=0.20,
            net_debt_to_ebitda=-1.0,
            ret_3m=0.08,
        ),
        ScoreInput(
            ticker="RICH",
            pctile_5y=90.0,
            ebitda_growth_1y=0.05,
            fcf_margin=0.10,
            net_debt_to_ebitda=1.0,
            ret_3m=0.02,
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
