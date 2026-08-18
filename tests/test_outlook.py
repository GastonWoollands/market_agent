from datetime import UTC, date, datetime

from agent.pack import assemble_pack, pack_hash, source_dicts, sources_from_counts
from api.outlook import build_outlook
from api.schemas import OutlookSource
from store.models import EventItem, NewsItem


class _Job:
    def __init__(self, name: str, status: str = "ok") -> None:
        self.job_name = name
        self.status = status
        self.started_at = datetime(2026, 8, 18, 11, 0, tzinfo=UTC)
        self.finished_at = datetime(2026, 8, 18, 11, 1, tzinfo=UTC)
        self.error = None


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
    assert payload.events[0].kind == "fomc"
    assert payload.sources[0].vendor == "yahoo"
    assert payload.sources[0].rows == 10
