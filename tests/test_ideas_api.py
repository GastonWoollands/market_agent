from datetime import date
from types import SimpleNamespace

from api.ideas import IdeasBoard

DAY = date(2026, 11, 6)


def _row(ident: int, ticker: str, **kwargs) -> tuple:
    instrument = SimpleNamespace(
        id=ident,
        ticker=ticker,
        name=kwargs.get("name", f"{ticker} Co"),
        sector=kwargs.get("sector", "Industrials"),
        industry=None,
    )
    metric = SimpleNamespace(
        as_of=kwargs.get("ttm_as_of", date(2026, 9, 30)),
        revenue=2_000_000_000,
        fcf=kwargs.get("fcf", 80_000_000),
        net_debt=kwargs.get("net_debt", 100_000_000),
        source="sec",
    )
    value = SimpleNamespace(
        as_of=DAY,
        ev=kwargs.get("ev", 1_000_000_000),
        ebitda=kwargs.get("ebitda", 200_000_000),
        ev_ebitda=kwargs.get("ev_ebitda", 5.0),
        pctile_5y=kwargs.get("pctile_5y", 12.0),
        ebitda_growth_1y=0.22,
        multiple_change_1y=-0.1,
        comparable=kwargs.get("comparable", True),
    )
    return instrument, metric, value


def _score(rank: int, *, trap: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        as_of=DAY,
        rank=rank,
        total=0.8,
        cheap=0.9,
        quality=0.7,
        change=0.6,
        setup=0.5,
        risk=0.05,
        trap=trap,
        fcf_margin=0.1,
        ret_12_1=38.3,
    )


def _board(**kwargs) -> IdeasBoard:
    rows = [
        _row(1, "GEM"),
        _row(2, "TOP", net_debt=-50_000_000, sector="Energy"),
        _row(3, "KODK", fcf=None),
        _row(4, "NEW", comparable=False, pctile_5y=None),
    ]
    exclusion = SimpleNamespace(
        reasons=[{"rule": "fcf_one_off", "values": {"fcf_yield": 0.79}}],
    )
    return IdeasBoard(
        rows,
        scores={1: (_score(2), None), 2: (_score(1, trap=True), None)},
        exclusions={3: exclusion},
        **kwargs,
    )


def test_every_member_gets_one_status_and_counts_add_up() -> None:
    tape = _board().build(stale=False)
    status = {item.ticker: item.status for item in tape.members}
    assert status == {"TOP": "ranked", "GEM": "ranked", "KODK": "excluded", "NEW": "no_score"}
    assert [item.ticker for item in tape.members] == ["TOP", "GEM", "KODK", "NEW"]
    assert (tape.universe_n, tape.with_data_n) == (4, 3)
    assert (tape.ranked_n, tape.excluded_n, tape.no_score_n) == (2, 1, 1)
    assert tape.excluded_by_rule == {"fcf_one_off": 1}
    assert tape.as_of == DAY
    assert tape.stale is False


def test_excluded_name_shows_the_rule_and_no_rank() -> None:
    tape = _board().build(stale=False)
    kodk = next(item for item in tape.members if item.ticker == "KODK")
    assert kodk.score is None
    assert kodk.exclusions[0].rule == "fcf_one_off"
    assert kodk.exclusions[0].values == {"fcf_yield": 0.79}
    assert kodk.fcf_yield is None


def test_ranked_member_carries_desk_metrics_and_12_1() -> None:
    tape = _board(fy_by_id={1: SimpleNamespace(cfo=10, net_income=12)}).build(stale=False)
    gem = next(item for item in tape.members if item.ticker == "GEM")
    assert gem.score is not None
    assert gem.score.rank == 2
    assert gem.score.ret_12_1 == 38.3
    assert gem.fcf_yield == 0.08
    assert gem.nd_ebitda == 0.5
    assert gem.accrual is False
    assert gem.exclusions == []


def test_shortlist_stats_use_ranked_names_only() -> None:
    tape = _board(shortlist_n=25).build(stale=False)
    stats = tape.shortlist
    assert stats.size == 2
    assert stats.median_ev_ebitda == 5.0
    assert stats.net_cash == 1
    assert stats.traps == 1
    assert [(item.sector, item.count) for item in stats.sectors] == [
        ("Energy", 1),
        ("Industrials", 1),
    ]


def test_no_ranked_names_is_stale() -> None:
    board = IdeasBoard([_row(1, "NEW", comparable=False)], scores={}, exclusions={})
    tape = board.build(stale=False)
    assert tape.stale is True
    assert tape.members[0].status == "no_score"
