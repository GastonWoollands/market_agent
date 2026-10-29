from datetime import UTC, datetime

import pytest

from ingest.fed_rss.errors import FedRssHttpError, FedRssParseError
from ingest.fed_rss.parse import EXCERPT_MAX, display_title, docs_from_rss, is_venue_excerpt

SPEECH_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Federal Reserve Speeches</title>
    <item>
      <title>Keynote remarks by Chairman Warsh at Jackson Hole</title>
      <link>https://www.federalreserve.gov/newsevents/speech/warsh20260828a.htm</link>
      <guid>https://www.federalreserve.gov/newsevents/speech/warsh20260828a.htm</guid>
      <pubDate>Fri, 28 Aug 2026 14:00:00 GMT</pubDate>
      <description>The 2 percent PCE target is firm, fixed. We have work to do.</description>
    </item>
  </channel>
</rss>
"""

MINUTES_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Monetary Policy</title>
    <item>
      <title>Minutes of the Federal Open Market Committee, July 28-29, 2026</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260819a.htm</link>
      <guid>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260819a.htm</guid>
      <pubDate>Wed, 19 Aug 2026 18:00:00 GMT</pubDate>
      <description></description>
    </item>
  </channel>
</rss>
"""

LONG_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Speeches</title>
    <item>
      <title>Remarks by Governor Example</title>
      <link>https://www.federalreserve.gov/newsevents/speech/example.htm</link>
      <guid>guid-long</guid>
      <pubDate>Thu, 27 Aug 2026 15:00:00 GMT</pubDate>
      <description><![CDATA[<p>%s</p>]]></description>
    </item>
  </channel>
</rss>
""" % ("word " * 400)


def test_speech_rss_sets_kind_speaker_and_excerpt() -> None:
    items = docs_from_rss(SPEECH_RSS, feed="speeches")
    assert len(items) == 1
    row = items[0]
    assert row.kind == "speech"
    assert row.speaker == "Chairman Warsh"
    assert row.excerpt is not None
    assert "work to do" in row.excerpt
    assert row.published_at == datetime(2026, 8, 28, 14, 0, tzinfo=UTC)
    assert row.url.endswith("warsh20260828a.htm")


def test_comma_title_sets_speaker_and_venue_excerpt_is_flagged() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Speeches</title>
    <item>
      <title>Warsh, In Our Time</title>
      <link>https://www.federalreserve.gov/newsevents/speech/warsh20260828a.htm</link>
      <guid>guid-warsh</guid>
      <pubDate>Fri, 28 Aug 2026 14:00:00 GMT</pubDate>
      <description>Speech At Jackson Hole, Wyoming</description>
    </item>
  </channel>
</rss>
"""
    items = docs_from_rss(xml, feed="speeches")
    assert items[0].speaker == "Warsh"
    assert display_title(items[0].title, items[0].speaker) == "Warsh: In Our Time"
    assert is_venue_excerpt(items[0].excerpt) is True


def test_minutes_title_overrides_statement_kind_and_empty_excerpt() -> None:
    items = docs_from_rss(MINUTES_RSS, feed="press_monetary")
    assert items[0].kind == "minutes"
    assert items[0].excerpt is None


def test_excerpt_truncates_and_strips_html() -> None:
    items = docs_from_rss(LONG_RSS, feed="speeches")
    assert items[0].excerpt is not None
    assert len(items[0].excerpt) == EXCERPT_MAX
    assert "<p>" not in items[0].excerpt


def test_empty_rss_raises() -> None:
    with pytest.raises(FedRssParseError, match="no usable"):
        docs_from_rss("<rss><channel></channel></rss>", feed="speeches")


def test_429_is_typed() -> None:
    err = FedRssHttpError("speeches: RSS rate limited", status_code=429)
    assert err.status_code == 429


STATEMENT_HTML = """<html><head><meta name="description" content="ignored"></head><body>
<div id="article">
  <div class="heading col-xs-12 col-sm-8 col-md-8">
    <p class="article__time">October 28, 2026</p>
    <h3 class="title">Federal Reserve issues FOMC statement</h3>
    <p class="releaseTime">For release at 2:00 p.m. EDT</p>
    <p>Share
  </div>
  <div class="col-xs-12 col-sm-8 col-md-8">
    <p>The Federal Open Market Committee approved the following statement
    for release by a 10 &#8211; 2 vote:</p>
    <p>The Committee decided to maintain the target range for the federal funds rate
    at 3-3/4 to 4 percent.</p>
    <p>Inflation remains elevated.</p>
    <p>&nbsp;</p>
    <p>Voting against the monetary policy action were Lisa D. Cook and Beth M. Hammack,
    who preferred to raise the target range.</p>
    <p>For media inquiries, please email <a href="#">[email protected]</a>.</p>
    <p><a href="/x.htm">Implementation Note issued October 28, 2026</a></p>
  </div>
</div>
<div id="lastUpdate" class="lastUpdate">Last Update: October 28, 2026</div>
</body></html>"""


def test_statement_body_keeps_vote_decision_and_dissent() -> None:
    from ingest.fed_rss.parse import body_from_html

    body = body_from_html(STATEMENT_HTML)
    assert body is not None
    assert body.startswith("The Federal Open Market Committee approved")
    assert "10 – 2 vote" in body
    assert "maintain the target range" in body
    assert body.endswith("who preferred to raise the target range.")
    for noise in ("Share", "For release", "media inquiries", "Implementation Note", "October 28"):
        assert noise not in body
    assert body_from_html("<html><p>no article</p></html>") is None
    assert len(body_from_html(STATEMENT_HTML, max_chars=40) or "") == 40


def test_fetch_body_refuses_non_fed_hosts() -> None:
    import httpx
    import pytest

    from ingest.fed_rss import FedRssClient
    from ingest.fed_rss.errors import FedRssParseError

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=STATEMENT_HTML)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with FedRssClient(client=http, rate=100.0) as client:
        with pytest.raises(FedRssParseError):
            client.fetch_body("https://example.com/monetary20261028a.htm")
        body = client.fetch_body(
            "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm"
        )
    assert calls == ["https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm"]
    assert body is not None and "10 – 2 vote" in body


def test_hike_dissent_reads_hawkish() -> None:
    from analytics.outlook_judgment import _stance

    text = "voting against were cook and hammack, who preferred to raise the target range"
    assert _stance(text) == "hawkish"
