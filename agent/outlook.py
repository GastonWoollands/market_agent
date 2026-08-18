"""Pack-grounded Outlook brief. The model only narrates; Python checks citations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent.brief import OutlookBrief
from agent.citations import citation_issues
from agent.errors import AgentError, CitationError
from agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from agent.providers import AgentClient

TEMPLATE_MODEL = "template"


@dataclass(frozen=True)
class WrittenBrief:
    body_md: str
    body_json: dict[str, Any]
    model: str
    prompt_version: str
    status: str


def user_prompt(pack: dict[str, Any]) -> str:
    blob = json.dumps(pack, default=str, sort_keys=True)
    return (
        "Write the Outlook brief from this evidence pack JSON. "
        "Return headline and body_md only.\n\n"
        f"{blob}"
    )


def render_markdown(brief: OutlookBrief) -> str:
    return f"{brief.headline.strip()}\n\n{brief.body_md.strip()}".strip()


def template_brief(pack: dict[str, Any]) -> OutlookBrief:
    as_of = pack.get("as_of") or "unavailable"
    header = _header_line(pack.get("header") or [])
    risk = _risk_line(pack.get("risk_on"))
    ten_year = _macro_line(pack.get("macro") or [], "DGS10", "10Y")
    event = _event_line(pack.get("events") or [])
    sources = _source_line(pack.get("sources") or [])
    body = (
        f"{header} {risk} {ten_year} {event} {sources} "
        "Not a trading signal. Fields not in the pack are unavailable."
    )
    return OutlookBrief(headline=f"Outlook {as_of} (template)", body_md=body.strip())


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
    issues = citation_issues(pack, text)
    if issues:
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


def _macro_line(rows: list[Any], series_id: str, label: str) -> str:
    for row in rows:
        if isinstance(row, dict) and row.get("series_id") == series_id:
            value = row.get("value")
            if value is None:
                return f"{label} unavailable."
            return f"{label} ({series_id}) {value}."
    return f"{label} unavailable."


def _event_line(rows: list[Any]) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = row.get("date")
        title = row.get("title")
        if day and title:
            return f"Next event {day}: {title}."
    return "Next event unavailable."


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
