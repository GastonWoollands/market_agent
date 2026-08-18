from datetime import UTC, date, datetime

from ingest.finnhub.parse import events_from_earnings
from ingest.news_rss.parse import headlines_from_rss
from jobs.ingest_calendar import events_from_yaml
from store.catalog import load_catalysts, load_news_queries

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Treasury yields hold near 4.7% - Reuters</title>
      <link>https://news.google.com/rss/articles/abc</link>
      <guid isPermaLink="false">guid-abc</guid>
      <pubDate>Tue, 18 Aug 2026 12:00:00 GMT</pubDate>
      <source url="https://www.reuters.com">Reuters</source>
    </item>
  </channel>
</rss>
"""


def test_news_queries_yaml_has_rates_and_inflation() -> None:
    catalog = load_news_queries()
    categories = {item.category for item in catalog.buckets}
    assert {"rates", "inflation", "sector", "growth"} <= categories
    assert all(item.queries for item in catalog.buckets)


def test_rss_parse_uses_guid_and_publisher() -> None:
    items = headlines_from_rss(RSS, category="rates", query="Treasury yields 10-year")
    assert len(items) == 1
    assert items[0].guid == "guid-abc"
    assert items[0].publisher == "Reuters"
    assert items[0].category == "rates"
    assert items[0].published_at == datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def test_catalysts_yaml_has_remaining_2026_fomc_and_cpi() -> None:
    catalog = load_catalysts()
    events = events_from_yaml(catalog)
    kinds = {item.kind for item in events}
    assert {"fomc", "cpi", "election"} <= kinds
    assert all(item.source == "yaml" for item in events)
    fomc_dates = {item.date for item in events if item.kind == "fomc"}
    assert date(2026, 9, 16) in fomc_dates
    assert date(2026, 12, 9) in fomc_dates
    cpi_dates = {item.date for item in events if item.kind == "cpi"}
    assert date(2026, 9, 11) in cpi_dates


def test_finnhub_earnings_filter_to_watchlist() -> None:
    payload = {
        "earningsCalendar": [
            {
                "date": "2026-08-20",
                "symbol": "AAPL",
                "hour": "amc",
                "epsEstimate": 1.5,
                "revenueEstimate": 90_000_000_000,
                "quarter": 3,
                "year": 2026,
            },
            {"date": "2026-08-20", "symbol": "ZZZZ", "hour": "bmo", "epsEstimate": 0.1},
        ]
    }
    events = events_from_earnings(payload, allowed={"AAPL", "NVDA"})
    assert len(events) == 1
    assert events[0].ticker == "AAPL"
    assert events[0].kind == "earnings"
    assert events[0].source == "finnhub"
    assert events[0].slug == "finnhub:AAPL:2026-08-20"
    assert "after close" in events[0].title


def test_empty_earnings_calendar_is_ok() -> None:
    assert events_from_earnings({"earningsCalendar": []}, allowed={"AAPL"}) == []
