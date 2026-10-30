from datetime import UTC, datetime

import pytest

from ingest.finnhub.errors import FinnhubParseError
from ingest.finnhub.parse import headlines_from_news, real_summary

OIL = "Oil set for fourth monthly gain as Hormuz tanker attack highlights supply risks"
WIRE = [
    {
        "id": 1,
        "datetime": 1793358060,
        "headline": f"{OIL} - Reuters",
        "summary": f"{OIL}  Reuters",
        "source": "Reuters",
        "url": "https://www.reuters.com/a",
    },
    {
        "id": 2,
        "datetime": 1793358000,
        "headline": "Aon CEO warns AI data center insurance risks could threaten financing",
        "summary": "Aon CEO Greg Case said concentration risk at AI data centers could constrain "
        "insurance capacity.",
        "source": "CNBC",
        "url": "https://www.cnbc.com/b",
    },
    {"id": 2, "datetime": 1793358000, "headline": "dup", "url": "https://x"},
    {"id": 3, "datetime": 0, "headline": "no time", "url": "https://y"},
    {"id": 4, "datetime": 1793358000, "headline": "", "url": "https://z"},
]


def test_headlines_from_news_keeps_real_summaries_only() -> None:
    rows = headlines_from_news(WIRE, category="wire", query="general")
    assert [row.guid for row in rows] == ["finnhub:1", "finnhub:2"]
    assert rows[0].summary is None  # wire row repeating its headline
    assert rows[1].summary and rows[1].summary.startswith("Aon CEO Greg Case")
    assert rows[1].publisher == "CNBC" and rows[1].category == "wire"
    assert rows[0].published_at == datetime.fromtimestamp(1793358060, UTC)


def test_real_summary_trims_long_text() -> None:
    text = real_summary("Headline", "word " * 200)
    assert text is not None and len(text) <= 400 and text.endswith("…")
    assert real_summary("Headline", "  ") is None
    cut = "Traders parse Amazon and Int"
    assert real_summary("Headline", cut) == cut + "…"
    assert real_summary("Headline", "Done.") == "Done."


def test_headlines_from_news_rejects_non_list() -> None:
    with pytest.raises(FinnhubParseError):
        headlines_from_news({"error": "bad"}, category="wire", query="general")
