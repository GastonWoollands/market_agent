from agent.citations import citation_issues
from agent.memos import name_pack, narrate_memo, template_memo


def _pack() -> dict:
    return name_pack(
        ticker="MSFT",
        name="Microsoft",
        rank=1,
        trap=False,
        pctile_5y=19.9,
        ev_ebitda=20.5,
        ebitda_growth_1y=0.327,
        fcf_yield=0.032,
        nd_ebitda=-0.4,
        accrual=True,
    )


def test_template_memo_is_fully_cited() -> None:
    pack = _pack()
    memo = template_memo(pack)
    text = " ".join([memo.why_scored, memo.what_10q_changed, memo.invalidation, memo.caveats])
    assert citation_issues(pack, text) == []
    assert "MSFT" in memo.why_scored
    assert "TSLA" not in text
    assert memo.what_10q_changed == "unavailable"
    assert "quality" not in text.lower()
    assert "sleeve" not in text.lower()
    assert "FCF yield 3.2%" in memo.why_scored


def test_narrate_memo_falls_back_when_agent_invents() -> None:
    pack = _pack()

    class _Client:
        provider = "anthropic"
        model = "claude-sonnet-5-5"

        def complete(self, *, system: str, user: str, schema=None):
            return schema(
                why_scored="Buy TSLA into 99.9%.",
                what_10q_changed="unavailable",
                invalidation="unavailable",
                caveats="unavailable",
            )

    written = narrate_memo(pack, client=_Client())
    assert written.status == "fallback"
    assert written.model == "template"
    assert "MSFT" in written.memo.why_scored


def test_narrate_memo_keeps_cited_agent_output() -> None:
    pack = _pack()

    class _Ok:
        provider = "gemini"
        model = "gemini-2.5-flash"

        def complete(self, *, system: str, user: str, schema=None):
            return schema(
                why_scored="MSFT EV/EBITDA 20.5 (19.9th %ile vs own 5y), FCF yield 3.2%.",
                what_10q_changed="unavailable",
                invalidation=(
                    "EV/EBITDA mean-reverts toward its 5y history or EBITDA growth 32.7% fades."
                ),
                caveats="Delayed data. Insider unavailable until Form 4.",
            )

    written = narrate_memo(pack, client=_Ok())
    assert written.status == "ok"
    assert written.model == "gemini/gemini-2.5-flash"
    assert written.memo.why_scored.startswith("MSFT")
