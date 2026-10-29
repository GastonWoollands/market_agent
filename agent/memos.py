"""Pack-grounded opportunity memos. Same agent SDKs as Outlook; no web tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from agent.citations import citation_issues
from agent.errors import AgentError
from agent.providers import AgentClient

MEMO_PROMPT_VERSION = "memo-v2"
MEMO_LIMIT = 20
MEMO_SYSTEM = """You write a short research memo for one US stock.

Rules:
- Narrate only fields in the name pack JSON.
- Use desk metrics in English: EV/EBITDA, 5y percentile, FCF yield,
  net debt / EBITDA, EBITDA growth.
- Do not mention quality, cheap, setup, insider, risk, total, or any 0-1 sleeve score.
- Do not use snake_case field names in prose.
- If a field is missing or null, write "unavailable". Do not invent a number.
- what_10q_changed must be "unavailable" unless the pack has a filing excerpt.
- Mention only the pack ticker. Do not name other firms.
- Every percentage you mention must be a number already in the pack.
- Not a trading signal. No buy/sell/hold. No price targets.
- No web search, no tools, no facts from outside the pack.
- English. Dense. Fill why_scored, what_10q_changed, invalidation, caveats.
"""


class OpportunityMemo(BaseModel):
    why_scored: str = Field(min_length=1)
    what_10q_changed: str = Field(min_length=1)
    invalidation: str = Field(min_length=1)
    caveats: str = Field(min_length=1)


@dataclass(frozen=True)
class WrittenMemo:
    memo: OpportunityMemo
    model: str
    prompt_version: str
    status: str
    pack: dict[str, Any]


def user_prompt(pack: dict[str, Any]) -> str:
    blob = json.dumps(pack, default=str, sort_keys=True)
    return (
        "Write the opportunity memo from this name pack JSON. "
        "Return why_scored, what_10q_changed, invalidation, caveats.\n\n"
        f"{blob}"
    )


def template_memo(pack: dict[str, Any]) -> OpportunityMemo:
    ticker = str(pack.get("ticker") or "unavailable")
    ev = pack.get("ev_ebitda")
    pctile = pack.get("pctile_5y")
    fcf_pct = pack.get("fcf_yield_pct")
    nd = pack.get("nd_ebitda")
    growth_pct = pack.get("ebitda_growth_pct")
    trap = pack.get("trap")
    accrual = pack.get("accrual")
    ev_s = "unavailable" if ev is None else str(ev)
    vs_own = "unavailable vs own 5y" if pctile is None else f"{pctile}th %ile vs own 5y"
    fcf_s = "unavailable" if fcf_pct is None else f"{fcf_pct}%"
    nd_s = "unavailable" if nd is None else f"{nd}x"
    growth_s = "unavailable" if growth_pct is None else f"{growth_pct}%"
    if accrual is True:
        accr_s = "cash from operations above net income"
    elif accrual is False:
        accr_s = "cash from operations not above net income"
    else:
        accr_s = "unavailable"
    trap_s = "trap (cheap vs history with falling EBITDA)" if trap else "not a trap"
    why = (
        f"{ticker} EV/EBITDA {ev_s} ({vs_own}), "
        f"FCF yield {fcf_s}, net debt / EBITDA {nd_s}, EBITDA 1y {growth_s}. "
        f"{trap_s}. Accrual {accr_s}. Not a trading signal."
    )
    invalid = (
        "Invalidation: EV/EBITDA mean-reverts toward its 5y history "
        f"or EBITDA growth {growth_s} fades."
    )
    caveats = "Delayed data. Insider unavailable until Form 4. 10-Q excerpt unavailable."
    return OpportunityMemo(
        why_scored=why,
        what_10q_changed="unavailable",
        invalidation=invalid,
        caveats=caveats,
    )


def narrate_memo(pack: dict[str, Any], *, client: AgentClient | None) -> WrittenMemo:
    if client is None:
        memo = template_memo(pack)
        model = "template"
        status = "fallback"
    else:
        try:
            parsed = client.complete(
                system=MEMO_SYSTEM, user=user_prompt(pack), schema=OpportunityMemo
            )
            memo = OpportunityMemo.model_validate(parsed)
            model = f"{client.provider}/{client.model}"
            status = "ok"
        except AgentError:
            memo = template_memo(pack)
            model = "template"
            status = "fallback"
    text = " ".join([memo.why_scored, memo.what_10q_changed, memo.invalidation, memo.caveats])
    issues = citation_issues(pack, text)
    if issues:
        memo = template_memo(pack)
        model = "template"
        status = "fallback"
    return WrittenMemo(
        memo=memo,
        model=model,
        prompt_version=MEMO_PROMPT_VERSION,
        status=status,
        pack=pack,
    )


def name_pack(
    *,
    ticker: str,
    name: str,
    rank: int,
    trap: bool,
    pctile_5y: float | None,
    ev_ebitda: float | None,
    ebitda_growth_1y: float | None,
    fcf_yield: float | None = None,
    nd_ebitda: float | None = None,
    accrual: bool | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    growth_pct = None if ebitda_growth_1y is None else round(ebitda_growth_1y * 100.0, 1)
    fcf_pct = None if fcf_yield is None else round(fcf_yield * 100.0, 1)
    return {
        "ticker": ticker,
        "name": name,
        "rank": rank,
        "trap": trap,
        "accrual": accrual,
        "pctile_5y": None if pctile_5y is None else round(pctile_5y, 1),
        "ev_ebitda": None if ev_ebitda is None else round(ev_ebitda, 1),
        "ebitda_growth_1y": None if ebitda_growth_1y is None else round(ebitda_growth_1y, 4),
        "ebitda_growth_pct": growth_pct,
        "fcf_yield": None if fcf_yield is None else round(fcf_yield, 4),
        "fcf_yield_pct": fcf_pct,
        "nd_ebitda": None if nd_ebitda is None else round(nd_ebitda, 2),
        "events": events or [],
    }
