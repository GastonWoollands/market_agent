from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from analytics.fomc import FomcVote, SepSnapshot

HOLD = (
    "The Committee decided to maintain the target range for the federal funds rate at "
    "3-3/4 to 4 percent. "
)
CUT = (
    "The Committee decided to lower the target range for the federal funds rate by 1/4 "
    "percentage point to 3-3/4 to 4 percent. "
)
OCT_2026 = (
    "The Federal Open Market Committee approved the following statement for release by a "
    "10 – 2 vote: " + HOLD + "Inflation remains elevated. Voting against the monetary policy "
    "action were Lisa D. Cook and Beth M. Hammack, who preferred to raise the target range for "
    "the federal funds rate by 1/4 percentage point at this meeting."
)


@dataclass
class _Item:
    published_at: datetime
    excerpt: str | None
    url: str | None


def _parse(text: str) -> FomcVote:
    vote = FomcVote.parse(text, published=date(2026, 1, 1), url=None)
    assert vote is not None
    return vote


def _people(vote: FomcVote) -> list[tuple[str, str | None]]:
    return [(item.name, item.direction) for item in vote.dissents]


def test_hawkish_dissent_with_tally() -> None:
    vote = _parse(OCT_2026)
    assert (vote.votes_for, vote.votes_against, vote.unanimous) == (10, 2, False)
    assert _people(vote) == [("Lisa D. Cook", "hike"), ("Beth M. Hammack", "hike")]
    assert (vote.decision, vote.target_range, vote.complete) == ("maintain", "3-3/4 to 4", True)
    assert vote.to_pack()["dissent_direction"] == "hike"


def test_split_dissent_comma_and_no_change_wording() -> None:
    # October 2025 wording: "at this meeting to lower" and "no change".
    vote = _parse(
        CUT + "Voting against this action were Stephen I. Miran, who preferred at this meeting "
        "to lower the target range for the federal funds rate by 1/2 percentage point, and "
        "Jeffrey R. Schmid, who preferred no change to the target range for the federal funds "
        "rate at this meeting."
    )
    assert _people(vote) == [("Stephen I. Miran", "cut"), ("Jeffrey R. Schmid", "hold")]
    assert vote.votes_against == 2
    assert vote.to_pack()["dissent_direction"] == "mixed"
    assert vote.dissents[1].preferred.startswith("no change")


def test_grouped_dissent_semicolon_wording() -> None:
    # December 2025 wording: one cut dissent, then two hold dissents as a group.
    vote = _parse(
        CUT + "Voting for the monetary policy action were Jerome H. Powell, Chair; John C. "
        "Williams, Vice Chair; Michael S. Barr. Voting against this action were Stephen I. "
        "Miran, who preferred to lower the target range for the federal funds rate by 1/2 "
        "percentage point at this meeting; and Austan D. Goolsbee and Jeffrey R. Schmid, who "
        "preferred no change to the target range for the federal funds rate at this meeting."
    )
    assert _people(vote) == [
        ("Stephen I. Miran", "cut"),
        ("Austan D. Goolsbee", "hold"),
        ("Jeffrey R. Schmid", "hold"),
    ]
    assert vote.voters_for == ("Jerome H. Powell", "John C. Williams", "Michael S. Barr")
    assert (vote.votes_for, vote.votes_against) == (3, 3)


def test_older_the_action_wording() -> None:
    vote = _parse(
        HOLD + "Voting against the action was Esther L. George, who preferred to raise the "
        "target range for the federal funds rate to 4 to 4-1/4 percent."
    )
    assert _people(vote) == [("Esther L. George", "hike")]


def test_unanimous_from_voters_list_or_zero_tally() -> None:
    listed = _parse(HOLD + "Voting for the monetary policy action were Jerome H. Powell, Chair.")
    assert (listed.unanimous, listed.votes_against, listed.complete) == (True, 0, True)
    tallied = _parse("Approved by a 12 – 0 vote: " + HOLD)
    assert (tallied.unanimous, tallied.votes_for) == (True, 12)


def test_truncated_body_is_marked_incomplete() -> None:
    vote = _parse("Approved by a 10 – 2 vote: " + HOLD + "The Committee will")
    assert vote.votes_against == 2
    assert vote.dissents == ()
    assert vote.complete is False


def test_non_decision_statement_is_not_a_vote() -> None:
    text = "The FOMC on Friday unanimously approved updates to its Statement on Longer-Run Goals."
    assert FomcVote.parse(text, published=date(2026, 1, 1), url=None) is None


def test_latest_prefers_newest_decision_over_older_dissent() -> None:
    items = [
        _Item(datetime(2026, 10, 28, 18, tzinfo=UTC), OCT_2026, "oct"),
        _Item(datetime(2026, 11, 1, 18, tzinfo=UTC), "Federal Reserve issues FOMC statement", None),
        _Item(
            datetime(2026, 12, 9, 19, tzinfo=UTC),
            HOLD + "Voting for the action were Jerome H. Powell, Chair.",
            "dec",
        ),
    ]
    vote = FomcVote.latest(items)
    assert vote is not None
    assert vote.url == "dec"
    assert vote.unanimous is True


def _year(year: int, value: str) -> tuple[date, Decimal]:
    return date(year, 1, 1), Decimal(value)


SEP_POINTS = {
    "FEDTARMDLR": [(date(2026, 6, 17), Decimal("3.1")), (date(2026, 9, 16), Decimal("3.2"))],
    # 2025 row left over from an older vintage must not appear.
    "FEDTARMD": [_year(2025, "4.4"), _year(2026, "4.1"), _year(2027, "4.1")],
    "FEDTARRH": [_year(2026, "4.4")],
    "JCXFEMD": [_year(2026, "3.4"), _year(2027, "2.5")],
}


def test_sep_snapshot_precomputes_gaps_in_decimal() -> None:
    sep = SepSnapshot.from_points(SEP_POINTS, as_of=date(2026, 11, 10))
    assert sep is not None
    pack = sep.to_pack(as_of=date(2026, 11, 10), dff=Decimal("3.88"))
    assert pack["as_of"] == "2026-09-16"
    assert pack["fed_funds"]["median"] == {"2026": 4.1, "2027": 4.1}
    assert pack["fed_funds"]["range_high"] == {"2026": 4.4}
    assert pack["core_pce_inflation"]["median"]["2027"] == 2.5
    assert pack["fed_funds_longer_run_median"] == 3.2
    assert (pack["median_current_year"], pack["median_next_year"]) == (4.1, 4.1)
    assert pack["median_vs_dff_bp"] == 22.0
    assert pack["implied_25bp_moves_current_year"] == 0.9
    assert pack["median_next_vs_current_bp"] == 0.0


def test_sep_snapshot_hidden_before_its_release() -> None:
    assert SepSnapshot.from_points(SEP_POINTS, as_of=date(2026, 9, 15)) is None


def test_sep_snapshot_none_without_release_series() -> None:
    points = {"FEDTARMD": [_year(2026, "4.1")]}
    assert SepSnapshot.from_points(points, as_of=date(2026, 11, 10)) is None
