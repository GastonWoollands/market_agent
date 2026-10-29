from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from ingest.polymarket.errors import PolymarketHttpError, PolymarketParseError
from ingest.polymarket.parse import snapshot_from_event
from ingest.polymarket.resolve import (
    OddsOccupancyError,
    drop_occupied,
    load_slot,
    month_successors,
    pending_odds_slug,
    plan_odds_upserts,
    ranked_open_slugs,
)
from store.canonical import OddsPoint
from store.catalog import PolymarketEvent, PolymarketPick

CPI_SEARCH = [
    {
        "slug": "core-cpi-yoy-september-2026",
        "title": "Core CPI YoY - September 2026",
        "closed": False,
        "active": True,
        "endDate": "2026-10-15T03:59:00Z",
    },
    {
        "slug": "core-cpi-mom-september-2026",
        "title": "Core CPI MoM - September 2026",
        "closed": False,
        "active": True,
        "endDate": "2026-10-15T03:59:00Z",
    },
    {
        "slug": "core-cpi-yoy-july-2026-20260714151811920",
        "title": "Core CPI YoY - July 2026",
        "closed": True,
        "active": True,
        "endDate": "2026-08-12T03:59:00Z",
    },
    {
        "slug": "core-cpi-mom-august-2026-1786474662954",
        "title": "Core CPI MoM - August 2026",
        "closed": True,
        "active": True,
    },
]

FED_SEARCH = [
    {
        "slug": "fed-decision-in-september-762",
        "closed": False,
        "endDate": "2026-09-16T00:00:00Z",
    },
    {
        "slug": "fed-decision-in-october-20260617190323537",
        "closed": False,
        "endDate": "2026-10-28T23:59:00Z",
    },
    {
        "slug": "fed-decision-in-december-20260729232808632",
        "closed": False,
        "endDate": "2026-12-09T00:00:00Z",
    },
    {"slug": "fed-decision-in-january", "closed": True, "endDate": "2026-01-28T00:00:00Z"},
]


def _open_payload(title: str) -> dict:
    return {
        "title": title,
        "closed": False,
        "active": True,
        "updatedAt": "2026-09-15T12:00:00Z",
        "markets": [
            {
                "question": title,
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.33", "0.67"],
                "closed": False,
                "active": True,
            }
        ],
    }


class FakeGamma:
    def __init__(self, events: dict[str, dict], search: list[dict]) -> None:
        self.events = events
        self.search = search
        self.fetched: list[str] = []
        self.searched: list[str] = []

    def fetch_event(self, slug: str) -> OddsPoint:
        self.fetched.append(slug)
        if slug not in self.events:
            raise PolymarketHttpError(f"{slug}: not found", status_code=404)
        return snapshot_from_event(slug, self.events[slug])

    def search_events(self, query: str) -> list[dict]:
        self.searched.append(query)
        return self.search


def test_ranked_open_slugs_skips_mom_and_closed() -> None:
    slugs = ranked_open_slugs(CPI_SEARCH, slug_prefix="core-cpi-yoy-", pick="soonest_end")
    assert slugs == ["core-cpi-yoy-september-2026"]


def test_ranked_open_slugs_fomc_soonest_and_second() -> None:
    prefix = "fed-decision-in-"
    soonest = ranked_open_slugs(FED_SEARCH, slug_prefix=prefix, pick="soonest_end")
    following = ranked_open_slugs(FED_SEARCH, slug_prefix=prefix, pick="second_soonest_end")
    assert soonest[0] == "fed-decision-in-september-762"
    assert following[0] == "fed-decision-in-october-20260617190323537"
    assert "fed-decision-in-january" not in soonest
    assert "fed-decision-in-january" not in following


def test_month_successors_from_dated_cpi_seed() -> None:
    seed = "core-cpi-yoy-august-2026-1786474662954"
    assert month_successors(seed, "core-cpi-yoy-")[:2] == [
        "core-cpi-yoy-september-2026",
        "core-cpi-yoy-september-2026-1786474662954",
    ]


def test_load_slot_rotates_closed_cpi_seed_to_open_yoy() -> None:
    seed = "core-cpi-yoy-august-2026-1786474662954"
    item = PolymarketEvent(
        slot="core_cpi_yoy",
        label="Core CPI YoY",
        category="inflation",
        query="core cpi",
        slug_prefix="core-cpi-yoy-",
        slug=seed,
    )
    client = FakeGamma(
        events={
            seed: {"title": "Core CPI YoY - August 2026", "closed": True, "markets": []},
            "core-cpi-yoy-september-2026": _open_payload("Core CPI YoY - September 2026"),
            "core-cpi-mom-september-2026": _open_payload("Core CPI MoM - September 2026"),
        },
        search=CPI_SEARCH[1:],
    )
    point = load_slot(client, item, today=date(2026, 9, 16))
    assert point.slot == "core_cpi_yoy"
    assert point.slug == "core-cpi-yoy-september-2026"
    assert point.implied_yes == Decimal("0.33")
    assert "core-cpi-mom-september-2026" not in client.fetched
    assert client.searched == []


def test_load_slot_uses_open_seed_without_search() -> None:
    item = PolymarketEvent(
        slot="recession",
        label="Recession",
        category="growth",
        query="us recession",
        slug_prefix="us-recession-by-end-of-",
        slug="us-recession-by-end-of-2026",
    )
    client = FakeGamma(
        events={"us-recession-by-end-of-2026": _open_payload("US recession by end of 2026?")},
        search=[],
    )
    point = load_slot(client, item, current_slug="us-recession-by-end-of-2026")
    assert point.slug == "us-recession-by-end-of-2026"
    assert client.searched == []


def test_load_slot_raises_when_no_open_prefix_match() -> None:
    item = PolymarketEvent(
        slot="core_cpi_yoy",
        label="Core CPI YoY",
        category="inflation",
        query="core cpi",
        slug_prefix="core-cpi-yoy-",
        slug="core-cpi-yoy-august-2026-1786474662954",
    )
    client = FakeGamma(
        events={
            "core-cpi-yoy-august-2026-1786474662954": {
                "title": "old",
                "closed": True,
                "markets": [],
            }
        },
        search=CPI_SEARCH[1:],
    )
    with pytest.raises(PolymarketParseError, match="no open market matching"):
        load_slot(client, item, today=date(2026, 7, 15))


def _fed_item(*, slot: str, pick: PolymarketPick, slug: str) -> PolymarketEvent:
    return PolymarketEvent(
        slot=slot,
        label=slot,
        category="rates",
        query="fed decision",
        slug_prefix="fed-decision-in-",
        pick=pick,
        slug=slug,
    )


def _odds(slot: str, slug: str) -> OddsPoint:
    return OddsPoint(
        slot=slot,
        slug=slug,
        question=slot,
        implied_yes=Decimal("0.5"),
        as_of=datetime(2026, 9, 18, tzinfo=UTC),
    )


def test_load_slot_second_soonest_does_not_stick_to_front() -> None:
    october = "fed-decision-in-october-20260617190323537"
    december = "fed-decision-in-december-20260729232808632"
    item = _fed_item(slot="next_fomc", pick="second_soonest_end", slug=october)
    search = [
        {
            "slug": october,
            "closed": False,
            "active": True,
            "endDate": "2026-10-28T23:59:00Z",
        },
        {
            "slug": december,
            "closed": False,
            "active": True,
            "endDate": "2026-12-09T00:00:00Z",
        },
    ]
    client = FakeGamma(
        events={
            october: _open_payload("Fed Decision in October?"),
            december: _open_payload("Fed Decision in December?"),
        },
        search=search,
    )
    point = load_slot(client, item, current_slug=october)
    assert point.slot == "next_fomc"
    assert point.slug == december
    assert client.searched == ["fed decision"]
    assert october not in client.fetched


def test_plan_odds_upserts_writes_leaver_before_taker() -> None:
    october = "fed-decision-in-october-20260617190323537"
    december = "fed-decision-in-december-20260729232808632"
    points = [
        _odds("front_fomc", october),
        _odds("next_fomc", december),
        _odds("recession", "us-recession-by-end-of-2026"),
    ]
    current = {
        "front_fomc": "fed-decision-in-september-762",
        "next_fomc": october,
        "recession": "us-recession-by-end-of-2026",
    }
    ordered, park_first = plan_odds_upserts(points, current)
    assert park_first is False
    assert [point.slot for point in ordered] == ["next_fomc", "recession", "front_fomc"]


def test_plan_odds_upserts_rejects_duplicate_slug() -> None:
    october = "fed-decision-in-october-20260617190323537"
    points = [_odds("front_fomc", october), _odds("next_fomc", october)]
    with pytest.raises(OddsOccupancyError, match="same slug"):
        plan_odds_upserts(points, {"next_fomc": october})


def test_plan_odds_upserts_rejects_slug_held_outside_batch() -> None:
    october = "fed-decision-in-october-20260617190323537"
    points = [_odds("front_fomc", october)]
    with pytest.raises(OddsOccupancyError, match="still held by next_fomc"):
        plan_odds_upserts(points, {"next_fomc": october})


def test_plan_odds_upserts_parks_on_slug_swap() -> None:
    points = [_odds("front_fomc", "b"), _odds("next_fomc", "a")]
    ordered, park_first = plan_odds_upserts(
        points, {"front_fomc": "a", "next_fomc": "b"}
    )
    assert park_first is True
    assert [point.slot for point in ordered] == ["front_fomc", "next_fomc"]
    assert pending_odds_slug("front_fomc") == "__pending__front_fomc"


def test_drop_occupied_keeps_writable_slots() -> None:
    october = "fed-decision-in-october-20260617190323537"
    points = [
        _odds("front_fomc", october),
        _odds("core_cpi_yoy", "core-cpi-yoy-september-2026"),
        _odds("recession", "us-recession-by-end-of-2026"),
    ]
    kept, dropped = drop_occupied(points, {"next_fomc": october})
    assert [point.slot for point in kept] == ["core_cpi_yoy", "recession"]
    assert dropped == [f"front_fomc: slug {october} still held by next_fomc"]
    plan_odds_upserts(kept, {"next_fomc": october})


def test_drop_occupied_keeps_first_on_duplicate_slug() -> None:
    points = [_odds("front_fomc", "a"), _odds("next_fomc", "a"), _odds("recession", "r")]
    kept, dropped = drop_occupied(points, {})
    assert [point.slot for point in kept] == ["front_fomc", "recession"]
    assert dropped == ["next_fomc: slug a already taken in this batch"]


def test_drop_occupied_leaves_swaps_to_the_planner() -> None:
    points = [_odds("front_fomc", "b"), _odds("next_fomc", "a")]
    kept, dropped = drop_occupied(points, {"front_fomc": "a", "next_fomc": "b"})
    assert len(kept) == 2 and dropped == []
