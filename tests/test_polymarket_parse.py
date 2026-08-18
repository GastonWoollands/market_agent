from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ingest.polymarket.errors import PolymarketParseError
from ingest.polymarket.parse import snapshot_from_event


def test_snapshot_reads_yes_price_from_json_strings() -> None:
    point = snapshot_from_event(
        "us-recession-by-end-of-2026",
        {
            "title": "US recession by end of 2026?",
            "closed": False,
            "active": True,
            "updatedAt": "2026-08-18T08:00:00Z",
            "liquidity": "41793.29",
            "markets": [
                {
                    "question": "US recession by end of 2026?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.075", "0.925"]',
                    "closed": False,
                    "active": True,
                    "liquidityNum": 41793.29,
                }
            ],
        },
    )
    assert point.implied_yes == Decimal("0.075")
    assert point.question == "US recession by end of 2026?"
    assert point.liquidity == Decimal("41793.29")
    assert point.as_of == datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    assert point.raw is not None
    assert point.raw["markets"][0]["yes"] == "0.075"


def test_snapshot_picks_most_likely_open_market() -> None:
    point = snapshot_from_event(
        "fed-decision-in-september-762",
        {
            "title": "Fed Decision in September?",
            "closed": False,
            "liquidity": "1000000",
            "markets": [
                {
                    "question": (
                        "Will the Fed decrease interest rates by 25 bps "
                        "after the September 2026 meeting?"
                    ),
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0.0095", "0.9905"],
                    "closed": False,
                    "active": True,
                },
                {
                    "question": (
                        "Will there be no change in Fed interest rates "
                        "after the September 2026 meeting?"
                    ),
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0.715", "0.285"],
                    "closed": False,
                    "active": True,
                },
                {
                    "question": "closed leftover",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0.99", "0.01"],
                    "closed": True,
                    "active": True,
                },
            ],
        },
    )
    assert point.implied_yes == Decimal("0.715")
    assert point.raw is not None
    assert len(point.raw["markets"]) == 2


def test_snapshot_rejects_closed_event() -> None:
    with pytest.raises(PolymarketParseError, match="closed"):
        snapshot_from_event(
            "fed-decision-in-september",
            {"title": "old", "closed": True, "markets": []},
        )
