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
