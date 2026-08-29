"""Python judgment object for Outlook. The writer only narrates these strings."""

from __future__ import annotations

from typing import Any

WATCH_PRINT = {
    "nfp": ("PAYEMS", "print_change"),
    "cpi": ("CPIAUCSL", "yoy_pct"),
    "pce": ("PCEPILFE", "yoy_pct"),
    "fomc": ("DFF", "value"),
}


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

    takeaways: list[str] = []
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

    watch: list[dict[str, Any]] = []
    for event in events[:5]:
        if not isinstance(event, dict):
            continue
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
            }
        )

    invalidation = None
    if pay_chg is not None and pay_chg < 0:
        invalidation = f"Second negative PAYEMS print_change after {pay_chg}."
    elif cpi_yoy is not None:
        invalidation = f"CPIAUCSL yoy_pct above {cpi_yoy}."

    abstract_parts = list(takeaways)
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
    }


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
