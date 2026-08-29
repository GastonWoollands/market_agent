from datetime import date
from decimal import Decimal

from analytics.macro_pack import count_changes, named_facts, series_row, yoy_mom_pct
from analytics.outlook_judgment import build_judgment
from store.catalog import FredSeriesItem


def test_yoy_mom_from_index() -> None:
    points = [
        (date(2025, 7, 1), Decimal("300")),
        (date(2025, 8, 1), Decimal("301")),
        (date(2026, 7, 1), Decimal("309")),
        (date(2026, 8, 1), Decimal("312")),
    ]
    yoy, mom = yoy_mom_pct(points)
    assert yoy == 3.65  # 312/301 - 1
    assert mom == 0.97  # 312/309 - 1


def test_count_changes_payrolls() -> None:
    points = [
        (date(2026, 5, 1), Decimal("159000")),
        (date(2026, 6, 1), Decimal("159120")),
        (date(2026, 7, 1), Decimal("159200")),
        (date(2026, 8, 1), Decimal("159340")),
    ]
    level, mom, avg = count_changes(points)
    assert level == 159340.0
    assert mom == 140.0
    assert avg == 113.3


def test_count_diff_weekly_sets_change_label() -> None:
    meta = FredSeriesItem(
        id="ICSA",
        name="Initial claims",
        unit="thousands",
        pack_view="count_diff",
        frequency="weekly",
        scale=0.001,
        spine=True,
    )
    points = [
        (date(2026, 8, 8), Decimal("220000")),
        (date(2026, 8, 15), Decimal("216000")),
    ]
    row = series_row(meta, points, as_of=date(2026, 8, 27))
    assert row["change_label"] == "weekly"
    assert row["print_change"] == -4.0
    assert row["value"] == 216.0
    assert row["spine"] is True


def test_series_row_index_yoy_uses_yoy_as_value() -> None:
    meta = FredSeriesItem(
        id="CPIAUCSL",
        name="CPI all items",
        unit="index",
        pack_view="index_yoy",
        frequency="monthly",
    )
    points = [
        (date(2025, 7, 1), Decimal("100")),
        (date(2026, 7, 1), Decimal("103")),
    ]
    row = series_row(meta, points, as_of=date(2026, 8, 27))
    assert row["value"] == 3.0
    assert row["yoy_pct"] == 3.0
    assert row["value_index"] == 103.0
    assert row["lag_days"] == 57
    assert row["stale"] is False
    stale = series_row(meta, points, as_of=date(2026, 10, 1))
    assert stale["lag_days"] == 92
    assert stale["stale"] is True


def test_named_facts_fed_vs_2y_and_curve_bp() -> None:
    facts = named_facts(
        [
            {"series_id": "DGS2", "value": 4.1},
            {"series_id": "DFF", "value": 4.33},
            {"series_id": "T10Y2Y", "value": 0.25, "w1_bp": 8.0},
            {"series_id": "DGS10", "value": 4.35, "w1_bp": 6.0},
            {"series_id": "DFII10", "value": 1.9},
            {"series_id": "T10YIE", "value": 2.45},
        ]
    )
    assert facts["fed_vs_2y_bp"] == -23.0
    assert facts["curve_2s10s_bp"] == 25.0
    assert facts["curve_2s10s_w1_bp"] == 8.0
    assert facts["dgs10_w1_bp"] == 6.0


def test_judgment_names_be_vs_cpi_and_watch_print() -> None:
    judgment = build_judgment(
        facts={"breakeven_10y": 2.32, "dgs10": 4.64, "curve_2s10s": 0.47},
        macro=[
            {"series_id": "CPIAUCSL", "yoy_pct": 3.3},
            {"series_id": "PAYEMS", "print_change": -23.0},
        ],
        odds=[
            {
                "label": "Sep FOMC",
                "top_outcome": "Hold",
                "top_implied_yes": 0.715,
            }
        ],
        events=[{"date": "2026-09-04", "title": "Employment Situation (August)", "kind": "nfp"}],
        risk_on={"score": 0.6},
    )
    assert judgment["regime"]["inflation"] == "market_below_trailing"
    assert judgment["regime"]["policy"] == "hold_base"
    assert any("3.3" in item for item in judgment["takeaways"])
    assert judgment["watch"][0]["last_print"] == "PAYEMS print_change -23.0"


def test_judgment_maps_boj_to_yen_and_ecb_to_deposit() -> None:
    judgment = build_judgment(
        facts={},
        macro=[
            {"series_id": "DEXJPUS", "value": 148.2},
            {"series_id": "ECBDFR", "value": 2.0},
        ],
        odds=[],
        events=[
            {"date": "2026-09-18", "title": "BoJ decision", "kind": "central_bank"},
            {"date": "2026-09-10", "title": "ECB decision", "kind": "central_bank"},
        ],
        risk_on=None,
        co_moves=[
            {
                "ids": ["DEXJPUS", "SMH"],
                "window": "1d",
                "changes": {"DEXJPUS": -1.2, "SMH": -2.1},
                "hint": "fx_jpy",
            }
        ],
    )
    assert judgment["watch"][0]["last_print"] == "DEXJPUS value 148.2"
    assert judgment["watch"][1]["last_print"] == "ECBDFR value 2.0"
    assert judgment["co_moves"][0]["hint"] == "fx_jpy"
