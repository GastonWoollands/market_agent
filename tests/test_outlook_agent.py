from datetime import date

import pytest

from agent.brief import OutlookBrief
from agent.citations import citation_issues, coverage_issues
from agent.errors import CitationError
from agent.outlook import narrate, render_markdown, template_brief
from agent.pack import assemble_pack
from agent.prompts import PROMPT_VERSION
from agent.providers import brief_from_text, make_client
from analytics.outlook_judgment import build_judgment
from store.settings import Settings


def _pack() -> dict:
    return assemble_pack(
        as_of=date(2026, 8, 18),
        header=[{"ticker": "^GSPC", "price": 5600.0, "change_pct": -0.12}],
        movers=[{"ticker": "XLK", "quadrant": "leading", "rs_ratio": 101.2, "ret_1m": 2.1}],
        macro=[
            {"series_id": "DGS10", "value": 4.68, "w1_bp": 6.0},
            {"series_id": "CPIAUCSL", "yoy_pct": 2.7, "mom_pct": 0.2, "as_of": "2026-07-01"},
            {
                "series_id": "ICSA",
                "print_change": -4.0,
                "mom_change": -4.0,
                "change_label": "weekly",
            },
        ],
        risk_on={"score": 0.4, "as_of": "2026-08-18", "stale": False},
        odds=[],
        news=[],
        events=[{"date": "2026-09-16", "title": "FOMC decision + SEP", "kind": "fomc"}],
        watchlist=[{"ticker": "NVDA", "change_pct": 1.2, "price": 180.0}],
        sources=[{"vendor": "yahoo", "job_name": "ingest_yahoo", "rows": 12}],
        facts={"dgs10": 4.68, "dgs10_w1_bp": 6.0, "curve_2s10s": 0.12},
    )


def _cited_brief() -> OutlookBrief:
    return OutlookBrief(
        headline="Tape",
        abstract="DGS10 4.68. CPIAUCSL yoy_pct 2.7. ICSA weekly print_change -4.0.",
        conclusions=["CPIAUCSL yoy_pct 2.7.", "ICSA weekly print_change -4.0."],
        expect="FOMC decision + SEP on 2026-09-16.",
        live_md="FOMC decision + SEP on 2026-09-16. DGS10 4.68.",
        macro_md="DGS10 4.68. CPIAUCSL yoy_pct 2.7. ICSA weekly print_change -4.0.",
        market_md="^GSPC 5600.0 (-0.12%). Risk-On 0.4. XLK leading.",
        near_term_md="FOMC decision + SEP on 2026-09-16.",
        tldr="Market consolidating ahead of FOMC decision.",
        what_happened=(
            "DGS10 led with a w1_bp of 6.0 to 4.68%, then ^GSPC followed at 5600.0 (-0.12%) "
            "while XLK stayed leading on the RRG."
        ),
        current_positioning="10Y at 4.68% with curve_2s10s 0.12 ahead of the FOMC.",
        drivers=(
            "Printed: CPIAUCSL yoy_pct 2.7 and ICSA weekly print_change -4.0. "
            "Next: FOMC decision + SEP on 2026-09-16."
        ),
        invalidation="Break below support invalidates consolidation.",
        macro_deep="DGS10 4.68%. CPIAUCSL yoy_pct 2.7%. ICSA weekly print_change -4.0.",
        market_deep="^GSPC 5600.0 (-0.12%). Risk-On 0.4. XLK leading.",
        policy_deep="FOMC decision + SEP on 2026-09-16.",
        geopolitical_deep=None,
        calendar=[],
    )


def test_citation_rejects_invented_ticker_and_percent() -> None:
    pack = _pack()
    text = render_markdown(_cited_brief())
    assert citation_issues(pack, text) == []
    assert citation_issues(pack, "^GSPC is 5600.0. DGS10 is 4.68%.") == []
    assert "ticker:TSLA" in citation_issues(pack, "TSLA ripped.")
    assert "pct:99.9%" in citation_issues(pack, "^GSPC printed 99.9%.")


def test_citation_allows_implied_yes_as_percent() -> None:
    pack = _pack()
    pack["odds"] = [
        {
            "slug": "how-many-fed-rate-cuts-in-2026",
            "label": "Fed cuts in 2026",
            "implied_yes": 0.8525,
            "as_of": "2026-08-19T09:55:52+00:00",
        }
    ]
    assert citation_issues(pack, "Cuts implied_yes 85.25%.") == []
    assert citation_issues(pack, "Cuts implied_yes 0.8525%.") == []
    assert "pct:99.9%" in citation_issues(pack, "Cuts implied_yes 99.9%.")


def test_citation_allows_pack_yoy() -> None:
    pack = _pack()
    assert citation_issues(pack, "CPIAUCSL yoy_pct 2.7%.") == []
    assert "pct:99.9%" in citation_issues(pack, "CPIAUCSL yoy_pct 99.9%.")


def test_coverage_requires_cpi_yoy_and_weekly_claims() -> None:
    pack = _pack()
    assert coverage_issues(pack, "CPIAUCSL yoy_pct 2.7 ICSA weekly") == []
    assert "coverage:CPIAUCSL_yoy" in coverage_issues(pack, "CPI only, no number, weekly")
    assert "coverage:ICSA_weekly" in coverage_issues(
        pack, "CPIAUCSL yoy_pct 2.7 ICSA print_change -4.0"
    )


def test_template_brief_uses_only_pack_numbers() -> None:
    pack = _pack()
    brief = template_brief(pack)
    text = render_markdown(brief)
    assert citation_issues(pack, text) == []
    assert "^GSPC" in brief.market_md
    assert "4.68" in brief.macro_md
    assert "2.7" in brief.macro_md
    assert "CPIAUCSL yoy_pct" in brief.macro_md
    assert "weekly print_change" in brief.macro_md
    assert "0.4" in brief.market_md
    assert brief.live_md
    assert "TSLA" not in text


def test_narrate_keeps_cited_agent_output() -> None:
    pack = _pack()

    class _Client:
        provider = "gemini"
        model = "gemini-2.5-flash"

        def complete(self, *, system: str, user: str) -> OutlookBrief:
            assert "evidence pack" in user
            return _cited_brief()

    written = narrate(pack, client=_Client())
    assert written.status == "ok"
    assert written.model == "gemini/gemini-2.5-flash"
    assert written.prompt_version == PROMPT_VERSION
    assert PROMPT_VERSION == "outlook-v14"
    assert "## TL;DR" in written.body_md
    assert "## Abstract" in written.body_md
    assert written.body_json["abstract"]


def test_narrate_keeps_implied_yes_percent() -> None:
    pack = _pack()
    pack["odds"] = [{"slug": "how-many-fed-rate-cuts-in-2026", "implied_yes": 0.8525}]

    class _Client:
        provider = "gemini"
        model = "gemini-2.5-flash"

        def complete(self, *, system: str, user: str) -> OutlookBrief:
            return _cited_brief().model_copy(
                update={"market_deep": "^GSPC 5600.0 (-0.12%). Cuts implied_yes 85.25%."}
            )

    written = narrate(pack, client=_Client())
    assert written.status == "ok"
    assert "85.25%" in written.body_md


def test_narrate_drops_uncited_agent_output(caplog: pytest.LogCaptureFixture) -> None:
    pack = _pack()

    class _Client:
        provider = "anthropic"
        model = "claude-sonnet-5-5"

        def complete(self, *, system: str, user: str) -> OutlookBrief:
            return _cited_brief().model_copy(
                update={
                    "abstract": "Buy TSLA into 99.9%.",
                    "live_md": "Buy TSLA into 99.9%.",
                    "macro_deep": "Buy TSLA into 99.9%.",
                }
            )

    with caplog.at_level("WARNING"):
        with pytest.raises(CitationError) as caught:
            narrate(pack, client=_Client())
    assert "ticker:TSLA" in caught.value.issues
    assert "pct:99.9%" in caught.value.issues
    assert "Buy TSLA into 99.9%." in caplog.text


def test_template_live_md_leads_with_policy_title() -> None:
    pack = _pack()
    pack["policy_items"] = [
        {
            "kind": "speech",
            "speaker": "Chairman Warsh",
            "title": "Keynote remarks by Chairman Warsh at Jackson Hole",
            "published_at": "2026-08-28T14:00:00+00:00",
            "excerpt": "price stability",
        }
    ]
    facts = dict(pack.get("facts") or {})
    facts["dgs2_d1_bp"] = 7.0
    facts["dgs30_d1_bp"] = -8.0
    pack["facts"] = facts
    pack["judgment"] = build_judgment(
        facts=facts,
        macro=pack.get("macro") or [],
        odds=pack.get("odds") or [],
        events=pack.get("events") or [],
        risk_on=pack.get("risk_on"),
        policy_items=pack["policy_items"],
        as_of=date(2026, 8, 29),
    )
    brief = template_brief(pack)
    assert "Keynote remarks by Chairman Warsh at Jackson Hole" in brief.headline
    assert "hawkish" in brief.headline
    assert "Keynote remarks by Chairman Warsh at Jackson Hole" in brief.live_md
    assert "stance hawkish" in brief.live_md
    assert "2026-08-28" in brief.live_md
    assert brief.expect.startswith("Next:")
    assert "Events:" not in brief.expect
    assert "ISM Services" not in brief.expect
    assert "stance unavailable" not in brief.headline
    assert "stance unavailable" not in brief.live_md
    assert citation_issues(pack, render_markdown(brief)) == []


def test_citation_rejects_speech_percent_absent_from_pack() -> None:
    pack = _pack()
    pack["policy_items"] = [
        {
            "kind": "speech",
            "title": "Keynote remarks by Chairman Warsh at Jackson Hole",
            "published_at": "2026-08-28T14:00:00+00:00",
            "excerpt": "The PCE target is firm, fixed.",
        }
    ]
    text = "Keynote remarks by Chairman Warsh at Jackson Hole. PCE ran 3.7%."
    assert "pct:3.7%" in citation_issues(pack, text)
    ok = "Keynote remarks by Chairman Warsh at Jackson Hole. DGS10 4.68."
    assert citation_issues(pack, ok) == []


def test_narrate_falls_back_to_template_without_client() -> None:
    written = narrate(_pack(), client=None)
    assert written.status == "fallback"
    assert written.model == "template"
    assert "Not a trading signal" in written.body_md
    assert "## Abstract" in written.body_md
    assert written.body_json["conclusions"]


def test_make_client_returns_none_without_keys() -> None:
    cfg = Settings(
        anthropic_api_key="",
        gemini_api_key="",
        google_api_key="",
        agent_provider="",
    )
    assert make_client(cfg) is None


def test_brief_from_text_strips_fences() -> None:
    expected = _cited_brief()
    brief = brief_from_text(f"```json\n{expected.model_dump_json()}\n```")
    assert brief == expected


def test_template_fallback_skips_prose_heuristics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent.citations.validate_brief_fields", lambda _brief: ["what_happened:too_short"]
    )
    written = narrate(_pack(), client=None)
    assert written.status == "fallback"


def _anthropic_agent(response: object, calls: list[dict]) -> object:
    from agent.providers import AnthropicAgent

    class _Messages:
        def parse(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return response

    agent = AnthropicAgent.__new__(AnthropicAgent)
    agent.model = "claude-sonnet-5-5"
    agent._client = type("C", (), {"messages": _Messages()})()
    return agent


def test_anthropic_default_is_sonnet_5_5_without_temperature() -> None:
    from types import SimpleNamespace

    from agent.providers import DEFAULT_MODELS

    assert DEFAULT_MODELS["anthropic"] == "claude-sonnet-5-5"
    calls: list[dict] = []
    brief = _cited_brief()
    agent = _anthropic_agent(SimpleNamespace(stop_reason="end_turn", parsed_output=brief), calls)
    assert agent.complete(system="s", user="u") == brief
    assert "temperature" not in calls[0]
    assert calls[0]["max_tokens"] >= 16000


def test_anthropic_refusal_falls_back() -> None:
    from types import SimpleNamespace

    from agent.errors import AgentError

    refusal = SimpleNamespace(
        stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"), parsed_output=None
    )
    agent = _anthropic_agent(refusal, [])
    with pytest.raises(AgentError, match="refusal"):
        agent.complete(system="s", user="u")


def test_citation_rejects_invented_precision_but_keeps_rounding() -> None:
    pack = {"facts": {"real_10y": 2.61, "dgs10": 4.99}, "odds": [{"implied_yes": 0.07}]}
    assert citation_issues(pack, "real_10y 2.6%.") == []
    assert citation_issues(pack, "real_10y 2.61%.") == []
    assert citation_issues(pack, "real_10y 2.64%.") == ["pct:2.64%"]
    assert citation_issues(pack, "10Y at 5.0%.") == []
    assert citation_issues(pack, "recession 7%.") == []
    assert citation_issues(pack, "recession 8%.") == ["pct:8%"]


def test_citation_allows_saar_unit() -> None:
    assert citation_issues({"macro": [{"value": 3.4}]}, "GDP 3.4 SAAR.") == []
