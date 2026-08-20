from datetime import date

import pytest

from agent.brief import OutlookBrief
from agent.citations import citation_issues
from agent.errors import CitationError
from agent.outlook import narrate, template_brief
from agent.pack import assemble_pack
from agent.providers import brief_from_text, make_client
from store.settings import Settings


def _pack() -> dict:
    return assemble_pack(
        as_of=date(2026, 8, 18),
        header=[{"ticker": "^GSPC", "price": 5600.0, "change_pct": -0.12}],
        movers=[{"ticker": "XLK", "quadrant": "leading", "rs_ratio": 101.2, "ret_1m": 2.1}],
        macro=[{"series_id": "DGS10", "value": 4.68}],
        risk_on={"score": 0.4, "as_of": "2026-08-18", "stale": False},
        odds=[],
        news=[],
        events=[{"date": "2026-09-16", "title": "FOMC decision + SEP", "kind": "fomc"}],
        watchlist=[{"ticker": "NVDA", "change_pct": 1.2, "price": 180.0}],
        sources=[{"vendor": "yahoo", "job_name": "ingest_yahoo", "rows": 12}],
    )


def test_citation_rejects_invented_ticker_and_percent() -> None:
    pack = _pack()
    assert citation_issues(pack, "^GSPC is 5600.0. DGS10 is 4.68%.") == []
    assert "ticker:TSLA" in citation_issues(pack, "TSLA ripped.")
    assert "pct:99.9%" in citation_issues(pack, "^GSPC printed 99.9%.")


def test_citation_allows_implied_yes_as_percent() -> None:
    pack = _pack()
    pack["odds"] = [
        {
            "slug": "how-many-fed-rate-cuts-in-2026",
            "implied_yes": 0.8525,
            "as_of": "2026-08-19T09:55:52+00:00",
        }
    ]
    assert citation_issues(pack, "Cuts implied_yes 85.25%.") == []
    assert citation_issues(pack, "Cuts implied_yes 0.8525%.") == []
    assert "pct:99.9%" in citation_issues(pack, "Cuts implied_yes 99.9%.")


def test_template_brief_uses_only_pack_numbers() -> None:
    pack = _pack()
    brief = template_brief(pack)
    text = f"{brief.headline}\n{brief.body_md}"
    assert citation_issues(pack, text) == []
    assert "^GSPC" in brief.body_md
    assert "4.68" in brief.body_md
    assert "0.4" in brief.body_md
    assert "TSLA" not in brief.body_md


def test_narrate_keeps_cited_agent_output() -> None:
    pack = _pack()

    class _Client:
        provider = "gemini"
        model = "gemini-2.5-flash"

        def complete(self, *, system: str, user: str) -> OutlookBrief:
            assert "evidence pack" in user
            return OutlookBrief(
                headline="Tape",
                body_md="^GSPC 5600.0 (-0.12%). DGS10 4.68%. Risk-On 0.4. XLK leading.",
            )

    written = narrate(pack, client=_Client())
    assert written.status == "ok"
    assert written.model == "gemini/gemini-2.5-flash"
    assert written.prompt_version == "outlook-v3"


def test_narrate_keeps_implied_yes_percent() -> None:
    pack = _pack()
    pack["odds"] = [{"slug": "how-many-fed-rate-cuts-in-2026", "implied_yes": 0.8525}]

    class _Client:
        provider = "gemini"
        model = "gemini-2.5-flash"

        def complete(self, *, system: str, user: str) -> OutlookBrief:
            return OutlookBrief(
                headline="Tape",
                body_md="^GSPC 5600.0 (-0.12%). Cuts implied_yes 85.25%.",
            )

    written = narrate(pack, client=_Client())
    assert written.status == "ok"
    assert "85.25%" in written.body_md


def test_narrate_drops_uncited_agent_output(caplog: pytest.LogCaptureFixture) -> None:
    pack = _pack()

    class _Client:
        provider = "anthropic"
        model = "claude-sonnet-4-5"

        def complete(self, *, system: str, user: str) -> OutlookBrief:
            return OutlookBrief(headline="Tape", body_md="Buy TSLA into 99.9%.")

    with caplog.at_level("WARNING"):
        with pytest.raises(CitationError) as caught:
            narrate(pack, client=_Client())
    assert "ticker:TSLA" in caught.value.issues
    assert "pct:99.9%" in caught.value.issues
    assert "Buy TSLA into 99.9%." in caplog.text


def test_narrate_falls_back_to_template_without_client() -> None:
    written = narrate(_pack(), client=None)
    assert written.status == "fallback"
    assert written.model == "template"
    assert "Not a trading signal" in written.body_md


def test_make_client_returns_none_without_keys() -> None:
    cfg = Settings(
        anthropic_api_key="",
        gemini_api_key="",
        google_api_key="",
        agent_provider="",
    )
    assert make_client(cfg) is None


def test_brief_from_text_strips_fences() -> None:
    brief = brief_from_text('```json\n{"headline": "Tape", "body_md": "^GSPC only."}\n```')
    assert brief.headline == "Tape"
    assert brief.body_md == "^GSPC only."
