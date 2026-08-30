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
        "Return headline, tldr, what_happened, current_positioning, drivers, watch_today, "
        "invalidation, macro_deep, market_deep, policy_deep, geopolitical_deep (optional), "
        "calendar, abstract, conclusions, expect, live_md, macro_md, market_md, near_term_md.\n\n"
        f"{blob}"
    )


def render_markdown(brief: OutlookBrief) -> str:
    bullets = "\n".join(f"- {item.strip()}" for item in brief.conclusions if item.strip())
    
    # Watch scenarios
    watch_section = ""
    if brief.watch_today:
        watch_items = []
        for scenario in brief.watch_today:
            date_str = f"{scenario.date} " if scenario.date else ""
            time_str = f" at {scenario.time}" if scenario.time else ""
            threshold_str = f" ({scenario.threshold})" if scenario.threshold else ""
            watch_items.append(
                f"### {scenario.catalyst}{date_str}{time_str}\n"
                f"**Bullish case{threshold_str}:** {scenario.outcome_bullish}\n\n"
                f"**Bearish case:** {scenario.outcome_bearish}"
            )
        watch_section = "\n\n".join(watch_items)
    
    # Calendar table
    calendar_section = ""
    if brief.calendar:
        calendar_rows = [
            "| Date | Time | Event | Consensus | Prior | Source |",
            "|------|------|-------|-----------|-------|--------|"
        ]
        for item in brief.calendar:
            date_str = item.date if item.date else "—"
            time_str = item.time if item.time else "—"
            cons_str = item.consensus if item.consensus else "—"
            prior_str = item.prior if item.prior else "—"
            source_str = item.source if item.source else "—"
            calendar_rows.append(
                f"| {date_str} | {time_str} | {item.event} | {cons_str} | {prior_str} | {source_str} |"
            )
        calendar_section = "\n".join(calendar_rows)
    
    # Build the complete markdown
    sections = [
        f"# {brief.headline.strip()}",
        "",
        "## TL;DR",
        brief.tldr.strip(),
        "",
        "---",
        "",
        "## What Happened",
        brief.what_happened.strip(),
        "",
        "## Current Positioning",
        brief.current_positioning.strip(),
        "",
        "## Drivers",
        brief.drivers.strip(),
        "",
        "---",
        "",
        "## Watch Today",
    ]
    
    if watch_section:
        sections.append(watch_section)
    else:
        sections.append("_No scheduled catalysts for today._")
    
    sections.extend([
        "",
        "---",
        "",
        "## Deep Dive",
        "",
        "### Macro",
        brief.macro_deep.strip(),
        "",
        "### Markets",
        brief.market_deep.strip(),
        "",
        "### Policy",
        brief.policy_deep.strip(),
    ])
    
    if brief.geopolitical_deep:
        sections.extend([
            "",
            "### Geopolitical & Energy",
            brief.geopolitical_deep.strip(),
        ])
    
    sections.extend([
        "",
        "---",
        "",
        "## What Would Invalidate This Read",
        brief.invalidation.strip(),
        "",
        "---",
    ])
    
    if calendar_section:
        sections.extend([
            "",
            "## Data Calendar",
            calendar_section,
            "",
        ])
    
    # Legacy sections (for backward compat, can be in collapsed details)
    sections.extend([
        "",
        "<details>",
        "<summary>Legacy sections</summary>",
        "",
        "## Abstract",
        brief.abstract.strip(),
        "",
        "## Conclusions",
        bullets,
        "",
        "## Expect",
        brief.expect.strip(),
        "",
        "## Live",
        brief.live_md.strip(),
    ])
    
    if brief.macro_md:
        sections.extend([
            "",
            "## Macro (legacy)",
            brief.macro_md.strip(),
        ])
    
    if brief.market_md:
        sections.extend([
            "",
            "## Market (legacy)",
            brief.market_md.strip(),
        ])
    
    if brief.near_term_md:
        sections.extend([
            "",
            "## Near term (legacy)",
            brief.near_term_md.strip(),
        ])
    
    sections.extend([
        "",
        "</details>",
    ])
    
    return "\n".join(sections).strip()


def template_brief(pack: dict[str, Any]) -> OutlookBrief:
    from agent.brief import WatchScenario, CalendarItem
    
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
    sources = _source_line(pack.get("sources") or [])
    macro = (
        f"{ten_year} {curve} {real} {be10} {fed2y} {cpi} {pce} {jobs} {claims} "
        f"{unrate} {debt} {ecb}"
    ).strip()
    market = f"{header} {risk} {odds}".strip()
    printed = _printed_line(pack, judgment)
    tape = _tape_line(pack, judgment, header, risk, odds)
    nxt = _next_line(judgment)
    expect = _watch_expect(judgment)
    near = f"{expect} {sources} Not a trading signal.".strip()
    headline = _headline(pack, judgment, as_of)
    live = " ".join(part for part in (printed, tape, nxt) if part).strip()
    abstract = " ".join(part for part in (tape, nxt) if part).strip() or macro
    conclusions = [part for part in (printed, tape, nxt) if part][:3] or [macro or "unavailable"]
    
    # New core sections (template fallback)
    tldr = f"{tape} {nxt}".strip() or "Market awaits catalysts. Template fallback active."
    
    # Extract key co_moves or outliers for what_happened
    what_happened = "Template fallback: "
    co_moves = judgment.get("co_moves") or []
    outliers = judgment.get("outliers") or []
    if co_moves and isinstance(co_moves, list) and co_moves:
        first_comove = co_moves[0]
        if isinstance(first_comove, dict):
            ids = first_comove.get("ids") or []
            changes = first_comove.get("changes") or {}
            if ids:
                what_happened += f"Co-move: {', '.join(str(i) for i in ids[:3])}. "
                what_happened += " ".join(f"{k} {v}" for k, v in list(changes.items())[:3]) + ". "
    if outliers and isinstance(outliers, list) and outliers:
        first_outlier = outliers[0]
        if isinstance(first_outlier, dict):
            what_happened += f"Outlier: {first_outlier.get('id')} {first_outlier.get('change')} (z={first_outlier.get('z')}). "
    if what_happened == "Template fallback: ":
        what_happened += f"{header} {risk}. Detailed cross-asset mechanism unavailable in template mode."
    
    # Current positioning
    positioning = f"Current levels: {curve} {real} {fed2y}"
    tensions = judgment.get("tensions") or []
    if tensions and isinstance(tensions, list) and tensions:
        first_tension = tensions[0]
        if isinstance(first_tension, dict):
            positioning += f" Tension: {first_tension.get('left')} vs {first_tension.get('right')}."
    if not positioning.strip():
        positioning = "Current positioning unavailable in template mode."
    
    # Drivers
    drivers = f"Printed: {printed or 'None'}. Tape: {tape or 'No significant moves'}. Next: {nxt or 'No scheduled tests'}."
    
    # Watch scenarios (template - just list next items)
    watch_scenarios: list[WatchScenario] = []
    watch_items = judgment.get("watch") or []
    if isinstance(watch_items, list):
        for item in watch_items:
            if isinstance(item, dict) and item.get("role") == "next" and item.get("title"):
                watch_scenarios.append(
                    WatchScenario(
                        catalyst=str(item.get("title")),
                        date=item.get("date"),
                        time=None,
                        outcome_bullish="Template: specific scenarios unavailable.",
                        outcome_bearish="Template: specific scenarios unavailable.",
                        threshold=item.get("last_print"),
                    )
                )
                if len(watch_scenarios) >= 3:
                    break
    
    # Invalidation
    invalidation_text = judgment.get("invalidation") or "Invalidation triggers unavailable in template mode."
    
    # Calendar
    calendar_items: list[CalendarItem] = []
    events = pack.get("events") or []
    if isinstance(events, list):
        for event in events[:5]:
            if isinstance(event, dict):
                calendar_items.append(
                    CalendarItem(
                        date=str(event.get("date") or ""),
                        time=None,
                        event=str(event.get("title") or ""),
                        consensus=None,
                        prior=None,
                        source=str(event.get("source") or ""),
                    )
                )
    
    return OutlookBrief(
        headline=headline,
        tldr=tldr,
        what_happened=what_happened,
        current_positioning=positioning,
        drivers=drivers,
        watch_today=watch_scenarios,
        invalidation=invalidation_text,
        macro_deep=macro or "Macro snapshot unavailable.",
        market_deep=market or "Market snapshot unavailable.",
        policy_deep=printed or "Policy communications unavailable.",
        geopolitical_deep=None,
        calendar=calendar_items,
        abstract=abstract or "unavailable",
        conclusions=conclusions,
        expect=expect or "unavailable",
        live_md=live or _live_md(pack),
        macro_md=macro or "",
        market_md=market or "",
        near_term_md=near or "",
    )


def _headline(pack: dict[str, Any], judgment: dict[str, Any], as_of: object) -> str:
    comms = judgment.get("policy_comms") if isinstance(judgment.get("policy_comms"), dict) else {}
    if isinstance(comms, dict) and comms.get("event"):
        stance = comms.get("stance")
        title = str(comms["event"])
        return f"{title}: {stance}" if stance else title
    row = _primary_policy(pack.get("policy_items") or [])
    if row and row.get("title"):
        return str(row["title"])
    for item in judgment.get("watch") or []:
        if isinstance(item, dict) and item.get("role") == "printed" and item.get("title"):
            return str(item["title"])
    return f"Outlook {as_of}"


def _printed_line(pack: dict[str, Any], judgment: dict[str, Any]) -> str:
    comms = judgment.get("policy_comms") if isinstance(judgment.get("policy_comms"), dict) else {}
    row = _primary_policy(pack.get("policy_items") or [])
    title = None
    day = None
    if isinstance(comms, dict):
        title = comms.get("event")
    if row:
        title = title or row.get("title")
        day = str(row.get("published_at") or "")[:10] or None
    if not title:
        for item in judgment.get("watch") or []:
            if isinstance(item, dict) and item.get("role") == "printed" and item.get("title"):
                title = item.get("title")
                day = item.get("date")
                break
    if not title:
        return ""
    bit = f"Printed: {title}"
    if day:
        bit = f"{bit} {day}"
    stance = comms.get("stance") if isinstance(comms, dict) else None
    if stance:
        bit = f"{bit}; stance {stance}"
    return f"{bit}."


def _tape_line(
    pack: dict[str, Any],
    judgment: dict[str, Any],
    header: str,
    risk: str,
    odds: str,
) -> str:
    facts = pack.get("facts") if isinstance(pack.get("facts"), dict) else {}
    parts: list[str] = []
    dgs10 = facts.get("dgs10")
    dgs10_w = facts.get("dgs10_w1_bp")
    if dgs10 is not None:
        bit = f"DGS10 {dgs10}"
        if dgs10_w is not None:
            bit = f"{bit} w1_bp {dgs10_w}"
        parts.append(bit)
    curve = facts.get("curve_2s10s")
    if curve is not None:
        parts.append(f"curve_2s10s {curve}")
    for item in judgment.get("tensions") or []:
        if isinstance(item, dict) and item.get("note") == "front_vs_long":
            parts.append(f"{item.get('left')} vs {item.get('right')}")
            break
    if "Risk-On unavailable" not in risk:
        parts.append(risk.rstrip("."))
    if "Odds unavailable" not in odds:
        parts.append(odds.rstrip("."))
    if not parts:
        return ""
    return "Tape: " + "; ".join(parts) + "."


def _next_line(judgment: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in judgment.get("watch") or []:
        if not isinstance(item, dict) or item.get("role") == "printed":
            continue
        if not item.get("title"):
            continue
        day = item.get("date") or ""
        parts.append(f"{day} {item['title']}".strip())
        if len(parts) >= 3:
            break
    if not parts:
        return ""
    return "Next: " + "; ".join(parts) + "."


def _primary_policy(items: object) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    ranked = [item for item in items if isinstance(item, dict) and item.get("title")]
    ranked.sort(key=lambda item: 0 if item.get("kind") == "speech" else 1)
    return ranked[0] if ranked else None


def _watch_expect(judgment: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in judgment.get("watch") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        if item.get("role") == "printed":
            continue
        day = item.get("date") or ""
        parts.append(f"{day} {item['title']}".strip())
        if len(parts) >= 3:
            break
    text = f"Next: {'; '.join(parts)}." if parts else ""
    odds_read = judgment.get("odds_read")
    if odds_read:
        text = f"{text} {odds_read}".strip()
    invalidation = judgment.get("invalidation")
    if invalidation:
        text = f"{text} Invalidation: {invalidation}".strip()
    return text


def _live_md(pack: dict[str, Any]) -> str:
    judgment = pack.get("judgment") if isinstance(pack.get("judgment"), dict) else {}
    parts: list[str] = []
    row = _primary_policy(pack.get("policy_items") or [])
    comms = judgment.get("policy_comms") if isinstance(judgment.get("policy_comms"), dict) else {}
    if row and row.get("title"):
        kind = row.get("kind") or "speech"
        published = str(row.get("published_at") or "")[:10]
        bit = f"{kind} {row['title']}"
        if published:
            bit = f"{bit} {published}"
        stance = comms.get("stance") if isinstance(comms, dict) else None
        if stance and stance != "unavailable":
            bit = f"{bit}; stance {stance}"
        parts.append(f"{bit}.")
    if isinstance(comms, dict):
        for item in comms.get("tensions") or []:
            if isinstance(item, dict) and item.get("note") == "front_vs_long":
                parts.append(f"{item.get('left')} vs {item.get('right')}.")
                break
    watch = judgment.get("watch") or []
    if isinstance(watch, list):
        for item in watch:
            if not isinstance(item, dict) or item.get("kind") == "speech":
                continue
            title = item.get("title")
            if not title:
                continue
            bit = str(title)
            day = item.get("date")
            last = item.get("last_print")
            if day:
                bit = f"{bit} {day}"
            if last:
                bit = f"{bit}; {last}"
            parts.append(f"{bit}.")
            break
    co_moves = judgment.get("co_moves") or []
    if isinstance(co_moves, list) and co_moves and isinstance(co_moves[0], dict):
        ids = ",".join(str(item) for item in (co_moves[0].get("ids") or [])[:3])
        changes = co_moves[0].get("changes") or {}
        if ids:
            change_bit = " ".join(f"{key} {value}" for key, value in list(changes.items())[:3])
            parts.append(f"co_moves {ids} {change_bit}.".strip())
    outliers = judgment.get("outliers") or []
    if not parts and isinstance(outliers, list) and outliers and isinstance(outliers[0], dict):
        row_out = outliers[0]
        parts.append(f"{row_out.get('id')} 1d {row_out.get('change')} z {row_out.get('z')}.")
    takeaways = judgment.get("takeaways") or []
    if isinstance(takeaways, list) and takeaways and not parts:
        parts.append(str(takeaways[0]))
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
    brief_json = brief.model_dump()
    
    # Run all validation checks
    from agent.citations import validate_brief_fields
    issues = (
        citation_issues(pack, text) + 
        coverage_issues(pack, text) + 
        validate_brief_fields(brief_json)
    )
    
    if issues:
        log.warning("validation check failed: %s\n%s", ", ".join(issues), text)
        raise CitationError(issues)
    return WrittenBrief(
        body_md=text,
        body_json=brief_json,
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
