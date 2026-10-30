from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from analytics.news_rank import NewsRules, bare_title, is_junk, select_news
from store.catalog import NewsSourcesFile, load_news_sources, publisher_key


@dataclass
class Row:
    category: str
    publisher: str
    stamp: str
    title: str
    query: str = ""

    @property
    def published_at(self) -> datetime:
        return datetime.fromisoformat(self.stamp).replace(tzinfo=UTC)


# Real Google News rows from 2026-10-29/30 (titles verbatim).
JUNK = [
    Row("corporate", "24/7 Wall St.", "2026-10-30T12:20",
        "Buy, Sell, or Hold? Today's Top Upgrades and Downgrades: Boston Scientific, DoorDash"
        " - 24/7 Wall St."),
    Row("corporate", "Microsoft", "2026-10-30T11:40",
        "FY27 Q1 - Press Releases - Investor Relations - Microsoft"),
    Row("fx", "Yahoo Finance UK", "2026-10-30T08:54",
        "US Dollar Index (DX-Y.NYB) charts, data and news - Yahoo Finance UK"),
    Row("commodities", "FXEmpire", "2026-10-30T06:36",
        "Gold and Silver Price Forecast: Silver Lags as Fed Hike Fears Grow - FXEmpire"),
    Row("fx", "Daily Pakistan", "2026-10-30T04:23",
        "Currency Exchange Rates in Pakistan Today: US Dollar, Pound, Euro, Riyal"
        " - 30 October 2026 - Daily Pakistan"),
    Row("inflation", "Mitrade", "2026-10-30T02:28",
        "What Is PCE? How Does It Impact Your Monthly Portfolio? - Mitrade"),
    Row("inflation", "Federal Reserve Bank of Atlanta", "2026-05-20T07:00",
        "What Is PCE? Explaining the Fed's Preferred Inflation Measure"
        " - Federal Reserve Bank of Atlanta"),
    Row("fx", "CurrencyNews.co.uk", "2026-10-29T20:31",
        "Pound Sterling Forecast: Falling UK Gilt Yields Lift GBP/EUR towards €1.20"
        " - CurrencyNews.co.uk"),
    Row("sector", "RealMoney Pro", "2026-10-29T15:05",
        "10 Stocks to Watch as the Rotation Builds - RealMoney Pro"),
    Row("fx", "The New Indian Express", "2026-10-29T04:21",
        "Rupee rises 11 paise to 95.17 against US dollar in early trade - The New Indian Express"),
]
NEWS = [
    Row("geo", "Reuters", "2026-10-30T09:35",
        "Brent 2026 view tops $90 for first time since May as MidEast stability remains elusive"
        " - Reuters"),
    Row("commodities", "The Armchair Trader", "2026-10-30T08:07",
        "Metals.io launches tokenised copper trading as demand grows - The Armchair Trader"),
    Row("commodities", "Bloomberg.com", "2026-10-30T07:03",
        "Gold Steadies Near $4,000 as Inflation Keeps Rate-Hike Bets Firm - Bloomberg.com"),
    Row("geo", "CNBC", "2026-10-30T06:33",
        "Iran claims four tankers struck mines in Hormuz as strike fears grow after U.S. midterms"
        " - CNBC"),
    Row("inflation", "The Korea Times", "2026-10-29T18:16",
        "US economy posts strong growth, inflation stubbornly high in challenge to Trump"
        " - The Korea Times"),
    Row("inflation", "France 24", "2026-10-29T13:36",
        "US economy posts strong growth, inflation stubbornly high in challenge to Trump"
        " - France 24"),
    Row("fiscal", "WSJ", "2026-10-29T13:58", "Federal Debt Hits 100% of GDP - WSJ"),
]
# Newer, unknown-tier geo rows that used to win on recency alone.
GEO_NOISE = [
    Row("geo", "Cyprus Mail", "2026-10-30T12:00", "Cyprus talks resume in Geneva - Cyprus Mail"),
    Row("geo", "Rural Radio Network", "2026-10-30T11:00",
        "Farm groups weigh trade risk - Rural Radio Network"),
]


@pytest.fixture(scope="module")
def rules() -> NewsRules:
    return NewsRules.from_catalog(load_news_sources())


def test_catalog_rules_drop_todays_junk_and_keep_the_news(rules: NewsRules) -> None:
    assert [row.title[:40] for row in JUNK if not is_junk(row, rules)] == []
    assert [row.title[:40] for row in NEWS if is_junk(row, rules)] == []


def test_tier_beats_recency_inside_a_bucket(rules: NewsRules) -> None:
    picked = select_news(NEWS + GEO_NOISE + JUNK, rules, per_bucket=1)
    by_bucket = {row.category: row.publisher for row in picked}
    assert by_bucket["geo"] == "Reuters"
    assert by_bucket["commodities"] == "Bloomberg.com"  # not tokenised copper
    two = select_news(NEWS + GEO_NOISE, rules, per_bucket=2)
    geo = [row.publisher for row in two if row.category == "geo"]
    assert geo == ["Reuters", "CNBC"]  # Hormuz kept over newer unknown-tier rows


def test_same_story_kept_once_from_the_better_source(rules: NewsRules) -> None:
    picked = select_news(NEWS, rules, per_bucket=3)
    inflation = [row.publisher for row in picked if row.category == "inflation"]
    assert inflation == ["France 24"]


def test_company_rows_bucket_per_ticker_and_wire_cap(rules: NewsRules) -> None:
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]
    company = [
        Row("company", "Yahoo", f"2026-10-30T0{hour}:00", f"{ticker} {words[hour]}", ticker)
        for ticker in ("AMZN", "NVDA")
        for hour in range(5)
    ]
    wire = [
        Row("wire", "Reuters", f"2026-10-30T0{hour}:00", f"wire {words[hour]} news")
        for hour in range(9)
    ]
    picked = select_news(company + wire, rules)
    counts: dict[str, int] = {}
    for row in picked:
        counts[row.query or row.category] = counts.get(row.query or row.category, 0) + 1
    assert counts == {"AMZN": 3, "NVDA": 3, "wire": 6}


def test_bare_title_strips_only_the_publisher_suffix() -> None:
    ir_page = bare_title("FY27 Q1 - Press Releases - Microsoft", "Microsoft")
    assert ir_page == "FY27 Q1 - Press Releases"
    assert bare_title("Fed holds - rates steady", "Reuters") == "Fed holds - rates steady"
    assert bare_title("Gold rises - Bloomberg.com", "Bloomberg") == "Gold rises"


def test_publisher_key_normalizes_spellings() -> None:
    assert publisher_key("Bloomberg.com") == publisher_key("Bloomberg") == "bloomberg"
    assert publisher_key("SeekingAlpha") == publisher_key("Seeking Alpha")
    assert publisher_key("www.tmgm.com") == "tmgm"


def test_catalog_rejects_a_publisher_in_two_lists() -> None:
    with pytest.raises(ValidationError):
        NewsSourcesFile.model_validate({"tiers": {1: ["Reuters"]}, "blocked": ["reuters"]})
    with pytest.raises(ValidationError):
        NewsSourcesFile.model_validate({"reject_title_patterns": ["("]})


def test_rss_query_carries_freshness_window() -> None:
    import httpx

    from ingest.news_rss import NewsClient

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["q"])
        return httpx.Response(200, text="<rss><channel></channel></rss>")

    with NewsClient(client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        # an empty feed inside the window is not an error
        assert client.fetch_query("oil prices", category="commodities", freshness_days=2) == []
    assert seen == ["oil prices when:2d"]
