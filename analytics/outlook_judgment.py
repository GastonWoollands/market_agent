"""Python judgment object for Outlook. The writer only narrates these strings."""

from __future__ import annotations

from datetime import date
from typing import Any

WATCH_PRINT = {
    "nfp": ("PAYEMS", "print_change"),
    "cpi": ("CPIAUCSL", "yoy_pct"),
    "pce": ("PCEPILFE", "yoy_pct"),
    "fomc": ("DFF", "value"),
    "speech": ("DGS2", "value"),
    "minutes": ("DFF", "value"),
    "treasury": ("DGS30", "value"),
}
WATCH_RANK = {
    "fomc": 0,
    "cpi": 1,
    "pce": 1,
    "nfp": 1,
    "speech": 2,
    "ism": 3,
    "minutes": 4,
    "beige_book": 5,
    "treasury": 6,
    "central_bank": 7,
    "gdp": 8,
    "jolts": 9,
}
RECENT_WATCH_KINDS = frozenset({"speech", "fomc", "minutes"})
FRONT_LONG_MIN_BP = 5.0


def _row(macro: list[dict[str, Any]], series_id: str) -> dict[str, Any]:
    for item in macro:
        if isinstance(item, dict) and item.get("series_id") == series_id:
            return item
    return {}


def _num(value: Any) -> float | None:
    return value if isinstance(value, int | float) else None


def _change(row: dict[str, Any]) -> float | None:
    if row.get("print_change") is not None:
        return _num(row.get("print_change"))
    return _num(row.get("mom_change"))


def build_judgment(
    *,
    facts: dict[str, Any],
    macro: list[dict[str, Any]],
    odds: list[dict[str, Any]],
    events: list[dict[str, Any]],
    risk_on: dict[str, Any] | None,
    outliers: list[dict[str, Any]] | None = None,
    co_moves: list[dict[str, Any]] | None = None,
    policy_items: list[dict[str, Any]] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    cpi = _row(macro, "CPIAUCSL")
    pce = _row(macro, "PCEPILFE")
    pay = _row(macro, "PAYEMS")
    icsa = _row(macro, "ICSA")
    be = _num(facts.get("breakeven_10y"))
    be5 = _num(facts.get("breakeven_5y"))
    fwd = _num(facts.get("forward_5y5y"))
    cpi_yoy = _num(cpi.get("yoy_pct"))
    pce_yoy = _num(pce.get("yoy_pct"))
    pay_chg = _change(pay)
    claims = _change(icsa)
    dgs10 = _num(facts.get("dgs10"))
    dgs10_w = _num(facts.get("dgs10_w1_bp"))
    dgs2_w = _num(facts.get("dgs2_w1_bp"))
    curve = _num(facts.get("curve_2s10s"))
    curve_w = _num(facts.get("curve_2s10s_w1_bp"))
    real = _num(facts.get("real_10y"))
    fed2y = _num(facts.get("fed_vs_2y_bp"))

    inflation = None
    if be is not None and cpi_yoy is not None:
        inflation = "market_below_trailing" if be < cpi_yoy else "market_above_trailing"
    labor = None
    if pay_chg is not None:
        labor = "one_weak_print" if pay_chg < 0 else "payrolls_positive"
    curve_regime = _curve_regime(curve_w, dgs2_w, dgs10_w)
    policy, odds_read = _policy_read(odds)

    tensions: list[dict[str, str]] = []
    if be is not None and cpi_yoy is not None:
        tensions.append(
            {
                "left": f"10Y BE {be}",
                "right": f"CPIAUCSL yoy_pct {cpi_yoy}",
                "note": inflation or "unavailable",
            }
        )
    if be is not None and be5 is not None and fwd is not None:
        tensions.append(
            {
                "left": f"breakeven_5y {be5}",
                "right": f"forward_5y5y {fwd}",
                "note": "long_run_anchor",
            }
        )
    if fed2y is not None:
        tensions.append(
            {
                "left": "DGS2 vs DFF",
                "right": f"fed_vs_2y_bp {fed2y}",
                "note": "front_end_vs_funds",
            }
        )

    comms = _policy_comms(policy_items, facts, odds)
    if comms:
        for item in reversed(comms.get("tensions") or []):
            if isinstance(item, dict) and item.get("left") and item.get("right"):
                tensions.insert(
                    0,
                    {
                        "left": str(item["left"]),
                        "right": str(item["right"]),
                        "note": str(item.get("note") or "policy"),
                    },
                )

    takeaways: list[str] = []
    if comms and comms.get("event"):
        stance = comms.get("stance")
        lead = str(comms["event"])
        if stance:
            lead = f"{lead} stance {stance}"
        takeaways.append(f"{lead}.")
        for item in comms.get("tensions") or []:
            if isinstance(item, dict) and item.get("note") == "front_vs_long":
                takeaways.append(f"{item.get('left')}. {item.get('right')}.")
                break
    if dgs10 is not None:
        w1 = f" w1_bp {dgs10_w}" if dgs10_w is not None else ""
        slope = f" curve_2s10s {curve}" if curve is not None else ""
        takeaways.append(f"DGS10 {dgs10}{w1}.{slope}.")
    if be is not None and cpi_yoy is not None:
        pce_bit = f" PCEPILFE yoy_pct {pce_yoy}." if pce_yoy is not None else ""
        takeaways.append(
            f"breakeven_10y {be} vs CPIAUCSL yoy_pct {cpi_yoy}.{pce_bit}"
        )
    if pay_chg is not None:
        takeaways.append(f"PAYEMS print_change {pay_chg}.")
    if claims is not None:
        label = icsa.get("change_label") or "weekly"
        takeaways.append(f"ICSA {label} print_change {claims}.")
    if odds_read:
        takeaways.append(odds_read)
    takeaways = takeaways[:4]

    ranked = sorted(
        [event for event in events if isinstance(event, dict)],
        key=lambda item: _watch_key(item, as_of),
    )
    watch: list[dict[str, Any]] = []
    for event in ranked[:5]:
        kind = str(event.get("kind") or "")
        last_print = None
        why = None
        pair = _watch_print(kind, str(event.get("title") or ""))
        if pair:
            series_id, key = pair
            row = _row(macro, series_id)
            value = row.get(key)
            if value is not None:
                last_print = f"{series_id} {key} {value}"
                why = f"last {series_id} {value}"
        watch.append(
            {
                "date": event.get("date"),
                "title": event.get("title"),
                "kind": kind,
                "last_print": last_print,
                "why": why,
                "role": _watch_role(event.get("date"), as_of),
            }
        )

    invalidation = None
    if pay_chg is not None and pay_chg < 0:
        invalidation = f"Second negative PAYEMS print_change after {pay_chg}."
    elif cpi_yoy is not None:
        invalidation = f"CPIAUCSL yoy_pct above {cpi_yoy}."

    abstract_parts = list(takeaways)
    if comms and comms.get("event") and takeaways:
        abstract_parts = list(takeaways[:2])
    if real is not None:
        abstract_parts.append(f"real_10y {real}.")
    score = None
    if isinstance(risk_on, dict):
        score = _num(risk_on.get("score"))
        if score is not None:
            abstract_parts.append(f"Risk-On {round(score, 2)}.")

    return {
        "takeaways": takeaways,
        "tensions": tensions,
        "regime": {
            "curve": curve_regime,
            "inflation": inflation,
            "labor": labor,
            "policy": policy,
        },
        "watch": watch,
        "invalidation": invalidation,
        "odds_read": odds_read,
        "abstract": " ".join(abstract_parts).strip() or "unavailable",
        "outliers": list(outliers or []),
        "co_moves": list(co_moves or []),
        "policy_comms": comms,
    }


def _watch_key(event: dict[str, Any], as_of: date | None) -> tuple[int, int, str]:
    kind = str(event.get("kind") or "")
    day = _event_day(event.get("date"))
    recent = 1
    if as_of is not None and day is not None:
        delta = (as_of - day).days
        if 0 <= delta <= 2 and kind in RECENT_WATCH_KINDS:
            recent = 0
    return (recent, WATCH_RANK.get(kind, 99), str(event.get("date") or ""))


def _policy_comms(
    items: list[dict[str, Any]] | None,
    facts: dict[str, Any],
    odds: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not items:
        return None
    ranked = [
        item for item in items if isinstance(item, dict) and item.get("title")
    ]
    ranked.sort(key=lambda item: 0 if item.get("kind") == "speech" else 1)
    first = ranked[0] if ranked else None
    if first is None:
        return None
    excerpt = first.get("excerpt") if isinstance(first.get("excerpt"), str) else None
    substance = excerpt if excerpt and not _venue_only(excerpt) else None
    blob = f"{first.get('title') or ''} {substance or ''}".lower()
    speaker = first.get("speaker") or _comma_speaker(str(first.get("title") or ""))
    event_name = _display_title(str(first.get("title") or ""), speaker)
    tensions: list[dict[str, str]] = []
    dgs2_d1 = _num(facts.get("dgs2_d1_bp"))
    dgs30_d1 = _num(facts.get("dgs30_d1_bp"))
    if _front_long_split(dgs2_d1, dgs30_d1):
        tensions.append(
            {
                "left": f"DGS2 d1_bp {dgs2_d1}",
                "right": f"DGS30 d1_bp {dgs30_d1}",
                "note": "front_vs_long",
            }
        )
    dgs2 = _num(facts.get("dgs2"))
    for row in odds:
        if not isinstance(row, dict):
            continue
        top = row.get("top_outcome")
        top_yes = row.get("top_implied_yes")
        label = row.get("label") or row.get("slug")
        if top is None or top_yes is None or dgs2 is None:
            continue
        tensions.append(
            {
                "left": f"{label} top_outcome {top} implied_yes {top_yes}",
                "right": f"DGS2 {dgs2}",
                "note": "odds_vs_front_end",
            }
        )
        break
    stance = _stance(blob)
    return {
        "event": event_name,
        "kind": first.get("kind"),
        "speaker": speaker,
        "stance": stance,
        "tensions": tensions,
    }


def _event_day(raw: object) -> date | None:
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _watch_role(raw: object, as_of: date | None) -> str:
    day = _event_day(raw)
    if as_of is None or day is None:
        return "next"
    return "printed" if day <= as_of else "next"


def _front_long_split(dgs2_d1: float | None, dgs30_d1: float | None) -> bool:
    if dgs2_d1 is None or dgs30_d1 is None:
        return False
    if dgs2_d1 * dgs30_d1 < 0:
        return abs(dgs2_d1) >= 3 or abs(dgs30_d1) >= 3
    return abs(dgs2_d1 - dgs30_d1) >= FRONT_LONG_MIN_BP


def _venue_only(text: str) -> bool:
    lower = text.strip().lower()
    return lower.startswith(("speech at", "remarks at", "testimony at", "statement at"))


def _comma_speaker(title: str) -> str | None:
    if "," not in title:
        return None
    name = title.split(",", 1)[0].strip()
    if name.isalpha() and name[:1].isupper() and len(name) > 1:
        return name
    return None


def _display_title(title: str, speaker: str | None) -> str:
    if "," in title:
        name, rest = title.split(",", 1)
        talk = rest.strip()
        if name.strip() and talk:
            return f"{name.strip()}: {talk}"
    if speaker and speaker not in title:
        return f"{speaker}: {title}"
    return title


def _stance(blob: str) -> str | None:
    if any(token in blob for token in ("work to do", "further tightening", "hike")):
        return "hawkish"
    if any(token in blob for token in ("cutting", "cut rates", "easing")):
        return "dovish"
    if "wait" in blob or "proceed carefully" in blob:
        return "wait"
    if "restrictive" in blob:
        return "restrictive"
    if "price stability" in blob or "firm, fixed" in blob:
        return "hawkish"
    return None


def _watch_print(kind: str, title: str) -> tuple[str, str] | None:
    pair = WATCH_PRINT.get(kind)
    if pair:
        return pair
    if kind != "central_bank":
        return None
    lower = title.lower()
    if "boj" in lower:
        return ("DEXJPUS", "value")
    if "boe" in lower:
        return ("DEXUSUK", "value")
    if "ecb" in lower:
        return ("ECBDFR", "value")
    return ("ECBDFR", "value")


def _curve_regime(
    curve_w: float | None, dgs2_w: float | None, dgs10_w: float | None
) -> str | None:
    if curve_w is None:
        return None
    if curve_w > 0 and dgs2_w is not None and dgs10_w is not None:
        if dgs2_w < dgs10_w:
            return "bull_steepener"
        return "bear_steepener"
    if curve_w < 0 and dgs2_w is not None and dgs10_w is not None:
        if dgs2_w < dgs10_w:
            return "bull_flattener"
        return "bear_flattener"
    if curve_w > 0:
        return "steepener"
    if curve_w < 0:
        return "flattener"
    return "unchanged"


def _policy_read(odds: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    policy = None
    bits: list[str] = []
    for row in odds:
        if not isinstance(row, dict):
            continue
        label = row.get("label") or row.get("slug")
        top = row.get("top_outcome")
        top_yes = row.get("top_implied_yes")
        yes = row.get("implied_yes")
        if top and top_yes is not None:
            bits.append(f"{label} top_outcome {top} implied_yes {top_yes}")
            if policy is None and "hold" in str(top).lower():
                policy = "hold_base"
            if policy is None and "no cut" in str(top).lower():
                policy = "hold_base"
        elif label and yes is not None:
            bits.append(f"{label} implied_yes {yes}")
    odds_read = "; ".join(bits[:2]) if bits else None
    return policy, odds_read
