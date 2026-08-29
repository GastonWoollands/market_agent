"""Pack-grounded Outlook brief. The model only narrates; Python checks citations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from agent.brief import OutlookBrief
from agent.citations import citation_issues, coverage_issues
from agent.errors import AgentError, CitationError
from agent.pack import writer_pack
from agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from agent.providers import AgentClient

log = logging.getLogger("agent.outlook")
TEMPLATE_MODEL = "template"


@dataclass(frozen=True)
class WrittenBrief:
    body_md: str
    body_json: dict[str, Any]
    model: str
    prompt_version: str
    status: str


def user_prompt(pack: dict[str, Any]) -> str:
    blob = json.dumps(writer_pack(pack), default=str, sort_keys=True)
    return (
        "Write the Outlook from this compact evidence pack JSON. "
        "Return headline, abstract, conclusions, expect, live_md, macro_md, "
        "market_md, and near_term_md.\n\n"
        f"{blob}"
    )


def render_markdown(brief: OutlookBrief) -> str:
    bullets = "\n".join(f"- {item.strip()}" for item in brief.conclusions if item.strip())
    return (
        f"{brief.headline.strip()}\n\n"
        f"## Abstract\n{brief.abstract.strip()}\n\n"
        f"## Conclusions\n{bullets}\n\n"
        f"## Expect\n{brief.expect.strip()}\n\n"
        f"## Live\n{brief.live_md.strip()}\n\n"
        f"## Macro\n{brief.macro_md.strip()}\n\n"
        f"## Market\n{brief.market_md.strip()}\n\n"
        f"## Near term\n{brief.near_term_md.strip()}"
    ).strip()


def template_brief(pack: dict[str, Any]) -> OutlookBrief:
    as_of = pack.get("as_of") or "unavailable"
    facts = pack.get("facts") if isinstance(pack.get("facts"), dict) else {}
    judgment = pack.get("judgment") if isinstance(pack.get("judgment"), dict) else {}
    header = _header_line(pack.get("header") or [])
    risk = _risk_line(pack.get("risk_on"))
    ten_year = _macro_sentence(pack, "DGS10", "10Y")
    curve = _fact_sentence(facts, "curve_2s10s", "curve_2s10s")
    real = _fact_sentence(facts, "real_10y", "real_10y")
    be10 = _fact_sentence(facts, "breakeven_10y", "breakeven_10y")
    fed2y = _fact_sentence(facts, "fed_vs_2y_bp", "fed_vs_2y_bp")
    cpi = _yoy_sentence(pack, "CPIAUCSL")
    pce = _yoy_sentence(pack, "PCEPILFE")
    jobs = _count_sentence(pack, "PAYEMS")
    claims = _count_sentence(pack, "ICSA")
    unrate = _macro_sentence(pack, "UNRATE", "UNRATE")
    debt = _macro_sentence(pack, "GFDEGDQ188S", "GFDEGDQ188S")
    ecb = _macro_sentence(pack, "ECBDFR", "ECBDFR")
    odds = _odds_line(pack.get("odds") or [])
    event = _event_line(pack.get("events") or [])
    sources = _source_line(pack.get("sources") or [])
    macro = (
        f"{ten_year} {curve} {real} {be10} {fed2y} {cpi} {pce} {jobs} {claims} "
        f"{unrate} {debt} {ecb}"
    ).strip()
    market = f"{header} {risk} {odds}".strip()
    near = f"{event} {sources} Not a trading signal.".strip()
    takeaways = [
        str(item)
        for item in (judgment.get("takeaways") or [])
        if isinstance(item, str) and item.strip()
    ]
    abstract = str(judgment.get("abstract") or "").strip() or macro
    expect = str(judgment.get("odds_read") or "").strip()
    invalidation = judgment.get("invalidation")
    if event:
        expect = f"{event} {expect}".strip()
    if invalidation:
        expect = f"{expect} Invalidation: {invalidation}".strip()
    if not expect:
        expect = near
    return OutlookBrief(
        headline=f"Outlook {as_of} (template)",
        abstract=abstract or "unavailable",
        conclusions=takeaways or [macro or "unavailable"],
        expect=expect or "unavailable",
        live_md=_live_md(pack, expect),
        macro_md=macro or "unavailable",
        market_md=market or "unavailable",
        near_term_md=near or "unavailable",
    )


def _live_md(pack: dict[str, Any], expect: str) -> str:
    judgment = pack.get("judgment") if isinstance(pack.get("judgment"), dict) else {}
    parts: list[str] = []
    watch = judgment.get("watch") or []
    if isinstance(watch, list) and watch and isinstance(watch[0], dict):
        title = watch[0].get("title")
        day = watch[0].get("date")
        last = watch[0].get("last_print")
        if title:
            bit = str(title)
            if day:
                bit = f"{bit} {day}"
            if last:
                bit = f"{bit}; {last}"
            parts.append(f"{bit}.")
    co_moves = judgment.get("co_moves") or []
    if isinstance(co_moves, list) and co_moves and isinstance(co_moves[0], dict):
        ids = ",".join(str(item) for item in (co_moves[0].get("ids") or [])[:3])
        changes = co_moves[0].get("changes") or {}
        if ids:
            change_bit = " ".join(f"{key} {value}" for key, value in list(changes.items())[:3])
            parts.append(f"co_moves {ids} {change_bit}.".strip())
    outliers = judgment.get("outliers") or []
    if not parts and isinstance(outliers, list) and outliers and isinstance(outliers[0], dict):
        row = outliers[0]
        parts.append(f"{row.get('id')} 1d {row.get('change')} z {row.get('z')}.")
    takeaways = judgment.get("takeaways") or []
    if isinstance(takeaways, list) and takeaways:
        parts.append(str(takeaways[0]))
    if expect:
        parts.append(expect)
    text = " ".join(part for part in parts if part).strip()
    return text or "unavailable"


def narrate(pack: dict[str, Any], *, client: AgentClient | None) -> WrittenBrief:
    if client is None:
        brief = template_brief(pack)
        model = TEMPLATE_MODEL
        status = "fallback"
    else:
        try:
            brief = client.complete(system=SYSTEM_PROMPT, user=user_prompt(pack))
            model = f"{client.provider}/{client.model}"
            status = "ok"
        except AgentError:
            brief = template_brief(pack)
            model = TEMPLATE_MODEL
            status = "fallback"
    text = render_markdown(brief)
    issues = citation_issues(pack, text) + coverage_issues(pack, text)
    if issues:
        log.warning("citation check failed: %s\n%s", ", ".join(issues), text)
        raise CitationError(issues)
    return WrittenBrief(
        body_md=text,
        body_json=brief.model_dump(),
        model=model,
        prompt_version=PROMPT_VERSION,
        status=status,
    )


def _header_line(rows: list[Any]) -> str:
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        price = row.get("price")
        change = row.get("change_pct")
        if ticker is None:
            continue
        if price is None:
            parts.append(f"{ticker} unavailable.")
            continue
        if change is None:
            parts.append(f"{ticker} {price}.")
        else:
            parts.append(f"{ticker} {price} ({change}%).")
    return " ".join(parts) if parts else "Header unavailable."


def _risk_line(risk_on: Any) -> str:
    if not isinstance(risk_on, dict) or risk_on.get("score") is None:
        return "Risk-On unavailable."
    as_of = risk_on.get("as_of") or "unavailable"
    return f"Risk-On {risk_on['score']} as of {as_of}."


def _macro_row(pack: dict[str, Any], series_id: str) -> dict[str, Any]:
    for row in pack.get("macro") or []:
        if isinstance(row, dict) and row.get("series_id") == series_id:
            return row
    return {}


def _macro_sentence(pack: dict[str, Any], series_id: str, label: str) -> str:
    row = _macro_row(pack, series_id)
    if not row:
        return f"{label} unavailable."
    value = row.get("value")
    w1 = row.get("w1_bp")
    if value is None:
        return f"{label} ({series_id}) unavailable."
    if w1 is None:
        return f"{label} ({series_id}) {value}."
    return f"{label} ({series_id}) {value} w1_bp {w1}."


def _fact_sentence(facts: dict[str, Any], key: str, label: str) -> str:
    value = facts.get(key)
    if value is None:
        return f"{label} unavailable."
    return f"{label} {value}."


def _yoy_sentence(pack: dict[str, Any], series_id: str) -> str:
    row = _macro_row(pack, series_id)
    if not row:
        return f"{series_id} unavailable."
    yoy = row.get("yoy_pct")
    mom = row.get("mom_pct")
    as_of = row.get("as_of") or "unavailable"
    if yoy is None:
        return f"{series_id} unavailable."
    if mom is None:
        return f"{series_id} yoy_pct {yoy} as of {as_of}."
    return f"{series_id} yoy_pct {yoy} mom_pct {mom} as of {as_of}."


def _count_sentence(pack: dict[str, Any], series_id: str) -> str:
    row = _macro_row(pack, series_id)
    if not row:
        return f"{series_id} unavailable."
    change = row.get("print_change")
    if change is None:
        change = row.get("mom_change")
    if change is None:
        return f"{series_id} unavailable."
    label = row.get("change_label") or "previous print"
    return f"{series_id} {label} print_change {change}."


def _odds_line(rows: list[Any]) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = row.get("label") or row.get("slug")
        top = row.get("top_outcome")
        top_yes = row.get("top_implied_yes")
        yes = row.get("implied_yes")
        if top and top_yes is not None:
            return f"{label} top_outcome {top} implied_yes {top_yes}."
        if label and yes is not None:
            return f"{label} implied_yes {yes}."
    return "Odds unavailable."


def _event_line(rows: list[Any]) -> str:
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = row.get("date")
        title = row.get("title")
        if day and title:
            parts.append(f"{day} {title}")
    if not parts:
        return "Next event unavailable."
    return "Events: " + "; ".join(parts) + "."


def _source_line(rows: list[Any]) -> str:
    parts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        vendor = row.get("vendor")
        count = row.get("rows")
        if vendor is None or count is None:
            continue
        parts.append(f"{vendor} {count}")
    if not parts:
        return "Sources unavailable."
    return "Sources: " + ", ".join(parts) + "."
