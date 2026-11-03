import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from analytics.positioning import PositioningRead
from analytics.prediction_markets import RangeDistribution, contract_mid
from api.odds import KalshiLiveView, fed_outcome_key
from api.schemas import LiveOdds, LiveOddsOutcome
from ingest.cftc.errors import CftcParseError
from ingest.cftc.parse import reports_from_rows
from ingest.kalshi.errors import KalshiParseError
from ingest.kalshi.parse import events_from_payload
from jobs.ingest_kalshi import KalshiSnapshotBuilder
from store.canonical import KalshiMarket
from store.catalog import load_cftc, load_kalshi

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 3, 15, 0, tzinfo=UTC)


def _event(series: str):
    return events_from_payload(json.loads((FIXTURES / f"kalshi_{series}.json").read_text()))[0]


def _series(slot: str):
    return next(item for item in load_kalshi().series if item.slot == slot)


def test_contract_mid_needs_a_bid() -> None:
    def market(bid: str, ask: str) -> KalshiMarket:
        return KalshiMarket(ticker="X", label="x", yes_bid=Decimal(bid), yes_ask=Decimal(ask))

    assert contract_mid(market("0.24", "0.25")) == pytest.approx(0.245)
    assert contract_mid(market("0", "0.01")) is None


def test_range_distribution_from_fixture() -> None:
    event = _event("KXINX")
    assert event.ticker == "KXINX-26NOV03H1600"
    distribution = RangeDistribution.from_markets(event.markets)
    assert distribution is not None
    assert sum(bucket.probability for bucket in distribution.buckets) == pytest.approx(1.0)
    assert distribution.buckets[0].low == 7200.0  # open "less" tail gets its neighbour's width
    assert distribution.buckets[-1].high == 7950.0
    assert distribution.mode.low == 7575.0
    p10, p50, p90 = (distribution.quantile(q) for q in (0.1, 0.5, 0.9))
    assert 7525 < p10 < p50 < p90 < 7650
    assert not distribution.thin


def test_range_distribution_flags_a_thin_book() -> None:
    markets = [
        KalshiMarket(
            ticker=f"B{low}",
            label="",
            strike_type="between",
            floor_strike=Decimal(low),
            cap_strike=Decimal(low + 24) + Decimal("0.9999"),
            yes_bid=Decimal("0.20") if low == 100 else Decimal(0),
            yes_ask=Decimal("0.30"),
        )
        for low in (75, 100, 125)
    ]
    distribution = RangeDistribution.from_markets(markets)
    assert distribution is not None and distribution.thin
    assert distribution.quantile(0.5) == pytest.approx(112.5)


def test_kalshi_parse_fails_loud_and_sorts_by_strike() -> None:
    with pytest.raises(KalshiParseError):
        events_from_payload({"cursor": ""})
    payload = json.loads((FIXTURES / "kalshi_KXINX.json").read_text())
    later = {**payload["events"][0], "event_ticker": "LATER", "strike_date": "2026-11-06T21:00:00Z"}
    payload["events"] = [later, payload["events"][0]]
    assert [event.ticker for event in events_from_payload(payload)] == [
        "KXINX-26NOV03H1600",
        "LATER",
    ]


def test_snapshot_builder_keys_fed_outcomes() -> None:
    point = KalshiSnapshotBuilder(_series("front_fomc"), now=NOW).build(_event("KXFEDDECISION"))
    assert point is not None and point.source == "kalshi" and point.slot == "front_fomc"
    keys = {market["key"]: market["yes"] for market in point.raw["markets"]}
    assert set(keys) == {"cut_50", "cut_25", "hold", "hike_25", "hike_50"}
    assert keys["hike_25"] == "0.745"
    assert keys["cut_25"] is None  # no bid


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (
            "Will the Fed increase interest rates by 25 bps after the December 2026 meeting?",
            "hike_25",
        ),
        (
            "Will the Fed decrease interest rates by 50+ bps after the December 2026 meeting?",
            "cut_50",
        ),
        ("Will there be no change in Fed interest rates after the December 2026 meeting?", "hold"),
        ("Who will chair the Fed?", None),
    ],
)
def test_fed_outcome_key(text: str, key: str | None) -> None:
    assert fed_outcome_key(text) == key


def _polymarket_fed(top: str) -> LiveOdds:
    return LiveOdds(
        slot="front_fomc",
        slug="fed-decision-in-december",
        label="Next FOMC",
        category="rates",
        question="Fed Decision in December?",
        implied_yes=0.725,
        outcomes=[LiveOddsOutcome(label=top, implied_yes=0.725)],
    )


def _kalshi_rows():
    fed = KalshiSnapshotBuilder(_series("front_fomc"), now=NOW).build(_event("KXFEDDECISION"))
    spx = KalshiSnapshotBuilder(_series("spx_close"), now=NOW).build(_event("KXINX"))
    return [
        SimpleNamespace(
            **point.model_dump(include={"slot", "question", "implied_yes", "raw"}), as_of=NOW
        )
        for point in (fed, spx)
    ]


def test_live_view_pairs_the_same_outcome_and_meeting() -> None:
    view = KalshiLiveView(_kalshi_rows(), load_kalshi(), now=NOW)
    december = "Will the Fed increase interest rates by 25 bps after the December 2026 meeting?"
    [item] = view.with_alt([_polymarket_fed(december)])
    assert item.alt is not None and item.alt.implied_yes == pytest.approx(0.745)
    january = december.replace("December", "January").replace("2026", "2027")
    [other] = view.with_alt([_polymarket_fed(january)])
    assert other.alt is None  # Kalshi's soonest meeting is December


def test_live_view_ranges_expire_at_the_close() -> None:
    rows = _kalshi_rows()
    open_ranges = {r.slot: r for r in KalshiLiveView(rows, load_kalshi(), now=NOW).ranges()}
    assert open_ranges["spx_close"].p50 is not None
    assert open_ranges["ndx_close"].unavailable == "No open range market."
    after = datetime(2026, 11, 3, 21, 5, tzinfo=UTC)
    closed = {r.slot: r for r in KalshiLiveView(rows, load_kalshi(), now=after).ranges()}
    assert closed["spx_close"].unavailable == "No open range market."


def test_cftc_fixture_parses_futures_only() -> None:
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    reports = reports_from_rows(rows)
    assert {report.contract_code for report in reports} == {"239742", "042601"}
    two_year = next(r for r in reports if r.contract_code == "042601")
    assert two_year.asset_mgr_long == 2532974
    combined = [{**rows[0], "futonly_or_combined": "Combined"}]
    assert reports_from_rows(combined) == []
    broken = [{**rows[0]}]
    del broken[0]["lev_money_positions_long"]
    with pytest.raises(CftcParseError, match="lev_money_positions_long"):
        reports_from_rows(broken)


def test_positioning_read_net_share_and_percentile() -> None:
    def row(week: int, asset_net: int) -> SimpleNamespace:
        return SimpleNamespace(
            report_date=date(2024, 1, 2).fromordinal(date(2024, 1, 2).toordinal() + 7 * week),
            open_interest=1000,
            asset_mgr_long=500 + asset_net,
            asset_mgr_short=500,
            lev_money_long=400,
            lev_money_short=600,
        )

    history = [row(week, week) for week in range(100)]
    read = PositioningRead.from_history(history)
    assert read is not None
    assert read.asset_managers.net == 99
    assert read.asset_managers.share_oi == pytest.approx(0.099)
    assert read.asset_managers.change_1w == 1
    assert read.asset_managers.pct_3y == 1.0
    assert read.leveraged_funds.share_oi == pytest.approx(-0.2)
    short = PositioningRead.from_history(history[:20])
    assert short is not None and short.asset_managers.pct_3y is None


def test_catalogs_load() -> None:
    assert load_cftc().codes() == ["13874+", "20974+", "239742", "042601", "043602", "1170E1"]
    assert set(load_kalshi().paired()) == {"front_fomc", "recession"}
