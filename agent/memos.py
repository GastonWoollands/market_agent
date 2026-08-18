"""Pack-grounded opportunity memos. Same agent SDKs as Outlook; no web tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from agent.citations import citation_issues
from agent.errors import AgentError
from agent.providers import AgentClient

MEMO_PROMPT_VERSION = "memo-v1"
MEMO_LIMIT = 20
MEMO_SYSTEM = """You write a short research memo for one US stock.

Rules:
- Narrate only fields in the name pack JSON.
- If a field is missing or null, write "unavailable". Do not invent a number.
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
    rank = pack.get("rank")
    total = pack.get("total")
    cheap = pack.get("cheap")
    quality = pack.get("quality")
    change = pack.get("change")
    setup = pack.get("setup")
    risk = pack.get("risk")
    trap = pack.get("trap")
    pctile = pack.get("pctile_5y")
    growth = pack.get("ebitda_growth_1y")
    growth_pct = pack.get("ebitda_growth_pct")
    why = (
        f"{ticker} ranks {rank} with total {total}. "
        f"Sleeves cheap {cheap}, quality {quality}, change {change}, setup {setup}. "
        f"Risk {risk}. Trap {trap}. Not a trading signal."
    )
    ten_q = (
        f"Four-quarter EBITDA growth {growth if growth is not None else 'unavailable'}"
        f"{'' if growth_pct is None else f' ({growth_pct}%)'}. "
        f"Own 5y EV/EBITDA percentile {pctile if pctile is not None else 'unavailable'}."
    )
    invalid = (
        f"Invalidation: percentile {pctile} mean-reverts higher or EBITDA growth "
        f"{growth if growth is not None else 'unavailable'} turns negative."
    )
    caveats = (
        "Insider sleeve is 0.5 because Form 4 is not ingested. "
        "Fields not in the pack are unavailable."
    )
    return OpportunityMemo(
        why_scored=why,
        what_10q_changed=ten_q,
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
    text = " ".join(
        [memo.why_scored, memo.what_10q_changed, memo.invalidation, memo.caveats]
    )
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
    total: float,
    cheap: float,
    quality: float,
    change: float,
    setup: float,
    insider: float,
    risk: float,
    trap: bool,
    pctile_5y: float | None,
    ev_ebitda: float | None,
    ebitda_growth_1y: float | None,
    fcf_margin: float | None,
    ret_3m: float | None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    growth_pct = None if ebitda_growth_1y is None else round(ebitda_growth_1y * 100.0, 1)
    ret_pct = None if ret_3m is None else round(ret_3m, 1)
    return {
        "ticker": ticker,
        "name": name,
        "rank": rank,
        "total": round(total, 4),
        "cheap": round(cheap, 4),
        "quality": round(quality, 4),
        "change": round(change, 4),
        "setup": round(setup, 4),
        "insider": round(insider, 4),
        "risk": round(risk, 4),
        "trap": trap,
        "pctile_5y": None if pctile_5y is None else round(pctile_5y, 1),
        "ev_ebitda": None if ev_ebitda is None else round(ev_ebitda, 1),
        "ebitda_growth_1y": None if ebitda_growth_1y is None else round(ebitda_growth_1y, 4),
        "ebitda_growth_pct": growth_pct,
        "fcf_margin": None if fcf_margin is None else round(fcf_margin, 4),
        "ret_3m": None if ret_3m is None else round(ret_3m, 4),
        "ret_3m_pct": ret_pct,
        "events": events or [],
    }
