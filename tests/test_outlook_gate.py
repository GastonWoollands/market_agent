from agent.citations import citation_issues
from agent.pack import writer_pack


def test_citation_gate_covers_sep_values() -> None:
    pack = {
        "sep": {
            "as_of": "2026-09-16",
            "fed_funds": {"median": {"2026": 4.1, "2027": 4.1}},
            "median_current_year": 4.1,
            "median_vs_dff_bp": 22.0,
        },
        "fomc_vote": {"votes_for": 10, "votes_against": 2, "dissenters": ["Lisa D. Cook"]},
    }
    assert citation_issues(pack, "The September SEP median is 4.1% for 2026.") == []
    assert citation_issues(pack, "The September SEP median is 4.6% for 2026.") == ["pct:4.6%"]


def test_citation_gate_checks_bp_and_vote_tally() -> None:
    pack = {
        "sep": {"median_vs_dff_bp": 22.0},
        "macro": [{"series_id": "DFF", "value": 3.88}],
        "yields_live": [{"d1_bp": -3.5}],
        "odds": [{"top_outcome": "Hike 25bp"}],
        "fomc_vote": {"votes_for": 10, "votes_against": 2},
    }
    ok = (
        "The median sits 22bp above DFF, the 3M bill fell 3.5bp, odds favor Hike 25bp, "
        "and October's hold was a 10-2 vote on 2026-10-28 at 3-3/4 to 4 percent."
    )
    assert citation_issues(pack, ok) == []
    bad = "The median sits 35bp above DFF after a 9 – 3 vote."
    assert citation_issues(pack, bad) == ["bp:35bp", "tally:9-3"]


def test_writer_pack_carries_sep_and_vote() -> None:
    sliced = writer_pack({"macro": [], "sep": {"as_of": "2026-09-16"}, "fomc_vote": {"date": "x"}})
    assert sliced["sep"] == {"as_of": "2026-09-16"}
    assert sliced["fomc_vote"] == {"date": "x"}
