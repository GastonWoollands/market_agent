from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from analytics.fomc import FomcVote, SepSnapshot

OCT_28 = (
    "The Federal Open Market Committee approved the following statement for release by a "
    "10 – 2 vote: The Committee decided to maintain the target range for the federal funds "
    "rate at 3-3/4 to 4 percent, in support of the Federal Reserve's dual mandate. Inflation "
    "remains elevated. Voting against the monetary policy action were Lisa D. Cook and "
    "Beth M. Hammack, who preferred to raise the target range for the federal funds rate by "
    "1/4 percentage point at this meeting."
)


@dataclass
class _Item:
    published_at: datetime
    excerpt: str | None
    url: str | None


def _year(year: int, value: str) -> tuple[date, Decimal]:
    return date(year, 1, 1), Decimal(value)


def test_vote_parses_tally_and_hawkish_dissent() -> None:
    vote = FomcVote.parse(OCT_28, published=date(2026, 10, 28), url="u")
    assert vote is not None
    assert (vote.votes_for, vote.votes_against) == (10, 2)
    assert vote.dissenters == ("Lisa D. Cook", "Beth M. Hammack")
    assert vote.dissent_direction == "hike"
    assert vote.decision == "maintain"
    assert vote.target_range == "3-3/4 to 4"
    assert vote.unanimous is False


def test_vote_reads_voters_list_and_single_dissent() -> None:
    text = (
        "The Committee decided to lower the target range for the federal funds rate to 3-1/2 "
        "to 3-3/4 percent. Voting for the monetary policy action were Jerome H. Powell, "
        "Chair; John C. Williams, Vice Chair; Michelle W. Bowman. Voting against this action "
        "was Jeffrey R. Schmid, who preferred to maintain the target range."
    )
    vote = FomcVote.parse(text, published=date(2026, 1, 1), url=None)
    assert vote is not None
    assert vote.decision == "lower"
    assert vote.dissenters == ("Jeffrey R. Schmid",)
    assert vote.dissent_direction == "hold"
    assert "Michelle W. Bowman" in vote.voters_for


def test_latest_vote_skips_title_only_statement() -> None:
    items = [
        _Item(datetime(2026, 9, 16, 18, tzinfo=UTC), "Federal Reserve issues FOMC statement", None),
        _Item(datetime(2026, 10, 28, 18, tzinfo=UTC), OCT_28, "oct"),
        _Item(datetime(2026, 11, 1, 18, tzinfo=UTC), None, None),
    ]
    vote = FomcVote.latest(items)
    assert vote is not None
    assert vote.url == "oct"
    assert vote.to_pack()["voters_for"] is None


def test_sep_snapshot_uses_release_date_and_drops_old_years() -> None:
    points = {
        "FEDTARMDLR": [(date(2026, 6, 17), Decimal("3.1")), (date(2026, 9, 16), Decimal("3.2"))],
        # 2025 row left over from an older vintage must not appear.
        "FEDTARMD": [_year(2025, "4.4"), _year(2026, "4.1"), _year(2027, "4.1")],
        "FEDTARRH": [_year(2026, "4.4")],
        "JCXFEMD": [_year(2026, "3.4"), _year(2027, "2.5")],
    }
    sep = SepSnapshot.from_points(points)
    assert sep is not None
    pack = sep.to_pack(as_of=date(2026, 11, 10), dff=3.88)
    assert pack["as_of"] == "2026-09-16"
    assert pack["fed_funds"]["median"] == {"2026": 4.1, "2027": 4.1}
    assert pack["fed_funds"]["range_high"] == {"2026": 4.4}
    assert pack["core_pce_inflation"]["median"]["2027"] == 2.5
    assert pack["fed_funds_longer_run_median"] == 3.2
    assert pack["median_current_year"] == 4.1
    assert pack["median_vs_dff_bp"] == 22.0


def test_sep_snapshot_none_without_release_series() -> None:
    assert SepSnapshot.from_points({"FEDTARMD": [_year(2026, "4.1")]}) is None
