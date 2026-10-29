from datetime import UTC, date, datetime

from agent.pack import (
    LIVE_NEAR_CATALYST_KINDS,
    assemble_pack,
    pack_hash,
    partition_events,
    policy_cutoff,
    source_dicts,
    sources_from_counts,
    writer_pack,
)
from api.outlook import build_outlook
from api.schemas import OutlookSource
from store.models import EventItem, NewsItem, OutlookReport


class _Job:
    def __init__(self, name: str, status: str = "ok") -> None:
        self.job_name = name
        self.status = status
        self.started_at = datetime(2026, 8, 18, 11, 0, tzinfo=UTC)
        self.finished_at = datetime(2026, 8, 18, 11, 1, tzinfo=UTC)
        self.error = None


def test_partition_events_keeps_next_cpi_outside_10d() -> None:
    as_of = date(2026, 8, 27)
    rows = [
        {"date": "2026-09-01", "title": "JOLTS (July)", "kind": "jolts", "source": "yaml"},
        {
            "date": "2026-09-04",
            "title": "Employment Situation (August)",
            "kind": "nfp",
            "source": "yaml",
        },
        {"date": "2026-09-11", "title": "CPI (August)", "kind": "cpi", "source": "yaml"},
        {"date": "2026-09-16", "title": "FOMC decision + SEP", "kind": "fomc", "source": "yaml"},
        {
            "date": "2026-10-02",
            "title": "Employment Situation (September)",
            "kind": "nfp",
            "source": "yaml",
        },
    ]
    near, later = partition_events(rows, as_of)
    kinds = [row["kind"] for row in near]
    assert kinds == ["jolts", "nfp", "cpi", "fomc"]
    assert later[0]["kind"] == "nfp"
    assert later[0]["date"] == "2026-10-02"


def test_partition_events_keeps_yesterday_speech_and_drops_far_ism() -> None:
    as_of = date(2026, 8, 29)
    rows = [
        {
            "date": "2026-08-28",
            "title": "Jackson Hole Chair keynote",
            "kind": "speech",
            "source": "yaml",
        },
        {"date": "2026-09-11", "title": "CPI (August)", "kind": "cpi", "source": "yaml"},
        {"date": "2026-09-16", "title": "FOMC decision + SEP", "kind": "fomc", "source": "yaml"},
        {
            "date": "2026-12-01",
            "title": "ISM Manufacturing (November)",
            "kind": "ism",
            "source": "yaml",
        },
    ]
    near, later = partition_events(rows, as_of)
    kinds = [row["kind"] for row in near]
    assert kinds == ["speech", "cpi", "fomc"]
    assert later[0]["kind"] == "ism"

    live_near, live_later = partition_events(
        rows,
        as_of,
        near_days=2,
        near_kinds=LIVE_NEAR_CATALYST_KINDS,
    )
    live_kinds = [row["kind"] for row in live_near]
    assert "speech" in live_kinds
    assert "cpi" in live_kinds
    assert "fomc" in live_kinds
    assert all(row["kind"] != "ism" for row in live_near)
    assert live_later[0]["kind"] == "ism"


def test_pack_hash_is_stable_and_sources_use_table_counts() -> None:
    jobs = [_Job("ingest_yahoo"), _Job("ingest_fred")]
    counts = {
        "daily_bars": 12,
        "macro_observations": 13,
        "odds_snapshots": 3,
        "news_items": 8,
        "earnings_events": 1,
        "yaml_events": 11,
        "rrg_points": 104,
    }
    rows = sources_from_counts(jobs, counts)
    by_vendor = {item.vendor: item for item in rows}
    assert by_vendor["yahoo"].rows == 12
    assert by_vendor["yahoo"].status == "ok"
    assert by_vendor["fred"].rows == 13
    assert by_vendor["catalysts"].job_name == "ingest_calendar"
    payload = assemble_pack(
        as_of=date(2026, 8, 18),
        header=[{"ticker": "^GSPC", "price": 5600.0}],
        movers=[{"ticker": "XLK", "quadrant": "leading"}],
        macro=[{"series_id": "DGS10", "value": 4.68}],
        risk_on={"score": 0.4},
        odds=[],
        news=[],
        events=[],
        watchlist=[],
        sources=source_dicts(rows),
    )
    assert pack_hash(payload) == pack_hash(payload)
    assert payload["opportunities"] == []
    assert payload["as_of"] == "2026-08-18"
    assert payload["sources"][0]["vendor"] == "yahoo"


def test_build_outlook_sources_and_stale_without_pack() -> None:
    news = [
        NewsItem(
            guid="g1",
            title="CPI preview",
            url="https://example.com/cpi",
            publisher="Reuters",
            published_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
            category="inflation",
            query="US CPI",
        )
    ]
    events = [
        EventItem(
            slug="yaml:2026-09-16:fomc",
            date=date(2026, 9, 16),
            title="FOMC decision + SEP",
            kind="fomc",
            source="yaml",
            ticker=None,
            extra=None,
        )
    ]
    sources = [OutlookSource(vendor="yahoo", job_name="ingest_yahoo", rows=10, status="ok")]
    payload = build_outlook(
        as_of=date(2026, 8, 18),
        now=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        news=news,
        events=events,
        sources=sources,
        pack=None,
    )
    assert payload.stale is True
    assert payload.brief is None
    assert payload.news[0].publisher == "Reuters"
    assert payload.policy_items == []
    assert payload.events[0].kind == "fomc"
    assert payload.events_later == []
    assert payload.sources[0].vendor == "yahoo"
    assert payload.sources[0].rows == 10


def test_build_outlook_attaches_stored_brief() -> None:
    report = OutlookReport(
        as_of=date(2026, 8, 18),
        model="gemini/gemini-2.5-flash",
        prompt_version="outlook-v1",
        body_md="Tape. DGS10 4.68%.",
        body_json={"headline": "Tape", "body_md": "DGS10 4.68%."},
        pack_id=1,
        status="ok",
    )
    payload = build_outlook(
        as_of=date(2026, 8, 18),
        now=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        news=[],
        events=[],
        sources=[],
        pack=None,
        report=report,
    )
    assert payload.brief == "Tape. DGS10 4.68%."
    assert payload.brief_status == "ok"
    assert payload.brief_model == "gemini/gemini-2.5-flash"


def test_writer_pack_keeps_yen_when_fresh_and_drops_lagged_jgb() -> None:
    payload = assemble_pack(
        as_of=date(2026, 8, 18),
        header=[],
        movers=[],
        macro=[
            {
                "series_id": "DEXJPUS",
                "value": 148.2,
                "region": "jp",
                "lag_days": 1,
            },
            {
                "series_id": "IRLTLT01JPM156N",
                "value": 1.1,
                "region": "jp",
                "lag_days": 80,
            },
            {"series_id": "DGS10", "value": 4.68, "spine": True, "region": "us"},
        ],
        risk_on=None,
        odds=[],
        news=[],
        events=[],
        watchlist=[],
        sources=[],
        drivers=[{"ticker": "SMH", "change_pct": -2.1}],
        judgment={
            "outliers": [{"id": "DEXJPUS", "window": "1d", "change": -1.2, "z": 2.1}],
            "co_moves": [],
        },
    )
    compact = writer_pack(payload)
    ids = {row["series_id"] for row in compact["macro"]}
    assert "DEXJPUS" in ids
    assert "IRLTLT01JPM156N" not in ids
    assert compact["drivers"][0]["ticker"] == "SMH"


def test_policy_cutoff_keeps_12h_drops_80h() -> None:
    as_of = date(2026, 8, 29)
    cutoff = policy_cutoff(as_of)
    fresh = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    stale = datetime(2026, 8, 25, 16, 0, tzinfo=UTC)
    assert fresh >= cutoff
    assert stale < cutoff


def test_writer_pack_keeps_three_policy_items() -> None:
    items = [
        {
            "published_at": f"2026-08-28T{index:02d}:00:00+00:00",
            "kind": "speech",
            "speaker": "Chairman Warsh",
            "title": f"Speech {index}",
            "url": "https://www.federalreserve.gov/speech",
            "excerpt": "price stability",
        }
        for index in range(5)
    ]
    payload = assemble_pack(
        as_of=date(2026, 8, 29),
        header=[],
        movers=[],
        macro=[],
        risk_on=None,
        odds=[],
        news=[],
        events=[],
        watchlist=[],
        sources=[],
        policy_items=items,
    )
    compact = writer_pack(payload)
    assert len(compact["policy_items"]) == 3
    assert compact["policy_items"][0]["title"] == "Speech 0"


def test_writer_pack_carries_regime_liquidity_anomalies_and_oil() -> None:
    payload = assemble_pack(
        as_of=date(2026, 10, 29),
        header=[],
        movers=[],
        macro=[
            {"series_id": "DCOILWTICO", "value": 103.37, "lag_days": 2, "region": "us"},
            {"series_id": "DHHNGSP", "value": 2.76, "lag_days": 2, "region": "us"},
        ],
        risk_on=None,
        odds=[],
        news=[],
        events=[],
        watchlist=[{"ticker": "AMZN", "change_pct": -3.8767, "price": 244.73}],
        sources=[],
    )
    payload["regime"] = {"growth": "slowdown", "confidence": {"growth": 0.5}}
    payload["liquidity"] = {"net_liquidity_bn": 5801.6, "wow_change_bn": -70.7}
    payload["anomalies"] = [
        {"type": "z_score_extreme", "severity": severity, "description": f"a{severity}"}
        for severity in (0.3, 0.92, 0.5, 0.7)
    ]
    compact = writer_pack(payload)
    assert compact["regime"]["growth"] == "slowdown"
    assert compact["liquidity"]["wow_change_bn"] == -70.7
    assert [row["severity"] for row in compact["anomalies"]] == [0.92, 0.7, 0.5]
    assert compact["watchlist"][0]["ticker"] == "AMZN"
    assert [row["series_id"] for row in compact["macro"]] == ["DCOILWTICO"]


def test_yields_live_rows_report_bp_not_percent() -> None:
    from datetime import UTC, datetime
    from decimal import Decimal
    from types import SimpleNamespace

    from agent.pack import yields_live_rows
    from store.catalog import LiveHeaderItem

    tape = {
        "^TNX": SimpleNamespace(
            quote_price=Decimal("4.989"),
            quote_change_pct=Decimal("-1.11001"),
            last_close=None,
            prev_close=None,
            as_of=datetime(2026, 10, 29, 18, 59, tzinfo=UTC),
        ),
        "^TYX": SimpleNamespace(
            quote_price=None,
            quote_change_pct=None,
            last_close=Decimal("5.329"),
            prev_close=Decimal("5.361"),
            as_of=None,
        ),
    }
    section = [
        LiveHeaderItem(ticker="^TNX", label="10Y"),
        LiveHeaderItem(ticker="^TYX", label="30Y"),
        LiveHeaderItem(ticker="^FVX", label="5Y"),
    ]
    rows = yields_live_rows(tape, section)
    assert [row["ticker"] for row in rows] == ["^TNX", "^TYX"]
    assert rows[0]["level"] == 4.989 and rows[0]["d1_bp"] == -5.6
    assert rows[1]["d1_bp"] == -3.2


def test_session_phase_by_eastern_clock() -> None:
    from datetime import UTC, datetime

    from agent.pack import session_phase

    day = date(2026, 10, 29)
    at = lambda h, m: datetime(2026, 10, 29, h, m, tzinfo=UTC)  # noqa: E731
    assert session_phase(day, at(12, 0))["phase"] == "pre_open"  # 08:00 ET
    assert session_phase(day, at(19, 0)) == {"phase": "intraday", "built_at_et": "2026-10-29 15:00"}
    assert session_phase(day, at(21, 5))["phase"] == "after_close"  # 17:05 ET
    assert session_phase(date(2026, 10, 28), at(14, 0))["phase"] == "after_close"
    saturday = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
    assert session_phase(date(2026, 10, 31), saturday)["phase"] == "closed"


def test_short_outcome_labels_every_fed_and_cpi_market() -> None:
    from agent.pack import short_outcome

    tail = " after the December 2026 meeting?"
    assert short_outcome("Will the Fed decrease interest rates by 50+ bps" + tail) == "Cut 50+"
    assert short_outcome("Will the Fed decrease interest rates by 25 bps" + tail) == "Cut 25bp"
    assert short_outcome("Will there be no change in Fed interest rates" + tail) == "Hold"
    assert short_outcome("Will the Fed increase interest rates by 25 bps" + tail) == "Hike 25bp"
    assert short_outcome("Will the Fed increase interest rates by 50+ bps" + tail) == "Hike 50+"
    assert short_outcome("Will 1 Fed rate cut happen in 2026?") == "1 cut in 2026"
    many = short_outcome("Will 12 or more Fed rate cuts happen in 2026?")
    assert many == "12 or more cuts in 2026"
    assert short_outcome("Will Core CPI YoY be 2.6% in October?") == "Core CPI YoY 2.6%"
    low = short_outcome("Will Core CPI YoY be 2.2% or less in October?")
    assert low == "Core CPI YoY 2.2% or less"
