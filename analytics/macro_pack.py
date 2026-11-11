"""Precomputed FRED snapshot for the Outlook pack. The writer does not compute."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from analytics.lookback import sort_points, window_deltas
from store.catalog import FredSeriesItem

Points = Sequence[tuple[date, Decimal]]

STALE_LAG_DAYS = {
    "daily": 2,
    "weekly": 10,
    "monthly": 80,
    "quarterly": 120,
}


def _num(value: Decimal | float | None, ndigits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), ndigits)


def _bp(delta: Decimal | None) -> float | None:
    if delta is None:
        return None
    return round(float(delta) * 100, 2)


def lag_days(as_of: date, last: date | None) -> int | None:
    if last is None:
        return None
    return (as_of - last).days


def is_stale(frequency: str, lag: int | None) -> bool:
    if lag is None:
        return True
    return lag > STALE_LAG_DAYS.get(frequency, 45)


def _month_shift(day: date, months: int) -> tuple[int, int]:
    index = day.year * 12 + day.month - 1 - months
    return index // 12, index % 12 + 1


def _by_month(points: Points) -> dict[tuple[int, int], Decimal]:
    return {(day.year, day.month): value for day, value in points}


def index_changes(points: Points) -> tuple[float | None, float | None, str | None]:
    """Monthly index: YoY vs the same month a year earlier, MoM vs the prior month.

    A gap in the source (e.g. no October 2025 CPI after the shutdown) must not fall back
    to an older print: that would label a 13-month change as YoY. The third value says
    why YoY is missing, so the writer and UI can say so.
    """
    ordered = sort_points(points)
    if not ordered:
        return None, None, None
    last_date, last = ordered[-1]
    if last == 0:
        return None, None, None
    months = _by_month(ordered)
    prev = months.get(_month_shift(last_date, 1))
    target = _month_shift(last_date, 12)
    year = months.get(target)
    mom = None if prev is None or prev == 0 else (last / prev - Decimal(1)) * 100
    yoy = None if year is None or year == 0 else (last / year - Decimal(1)) * 100
    note = None
    if year is None:
        first = ordered[0][0]
        label = f"{target[0]}-{target[1]:02d}"
        if (first.year, first.month) > target:
            note = f"{label} print is outside the loaded window; YoY unavailable"
        else:
            note = f"no {label} print in source; YoY unavailable"
    return _num(yoy, 2), _num(mom, 2), note


def yoy_mom_pct(points: Points) -> tuple[float | None, float | None]:
    yoy, mom, _ = index_changes(points)
    return yoy, mom


def count_changes(points: Points) -> tuple[float | None, float | None, float | None]:
    """Level, previous-print change, average of last three changes."""
    ordered = sort_points(points)
    if not ordered:
        return None, None, None
    last = ordered[-1][1]
    diffs = [ordered[i][1] - ordered[i - 1][1] for i in range(1, len(ordered))]
    mom = diffs[-1] if diffs else None
    last3 = diffs[-3:]
    avg = (sum(last3) / len(last3)) if last3 else None
    return _num(last, 1), _num(mom, 1), _num(avg, 1)


def _scaled_points(points: Points, scale: float) -> list[tuple[date, Decimal]]:
    ordered = sort_points(points)
    if not ordered or scale == 1:
        return ordered
    factor = Decimal(str(scale))
    return [(day, value * factor) for day, value in ordered]


def series_row(
    meta: FredSeriesItem,
    points: Points,
    *,
    as_of: date,
) -> dict[str, Any]:
    ordered = _scaled_points(points, meta.scale)
    last_date = ordered[-1][0] if ordered else None
    last = ordered[-1][1] if ordered else None
    d1, w1, m1, _y1 = window_deltas(ordered) if ordered else (None, None, None, None)
    lag = lag_days(as_of, last_date)
    view = meta.pack_view
    value_digits = 1 if meta.frequency == "quarterly" and meta.unit == "percent" else 4
    if view == "yield_bp":
        value_digits = 2
    row: dict[str, Any] = {
        "series_id": meta.id,
        "name": meta.name,
        "unit": meta.unit,
        "category": meta.category,
        "region": meta.region,
        "frequency": meta.frequency,
        "pack_view": view,
        "spine": meta.spine,
        "as_of": last_date.isoformat() if last_date else None,
        "lag_days": lag,
        "stale": is_stale(meta.frequency, lag),
        "insight": meta.insight,
        "value": _num(last, value_digits),
    }
    if view == "yield_bp":
        row["d1_bp"] = _bp(d1)
        row["w1_bp"] = _bp(w1)
        row["m1_bp"] = _bp(m1)
    elif view == "index_yoy":
        yoy, mom, note = index_changes(ordered)
        row["value_index"] = _num(last)
        row["yoy_pct"] = yoy
        row["mom_pct"] = mom
        row["value"] = yoy
        if note:
            row["yoy_note"] = note
    elif view == "count_diff":
        level, mom, avg = count_changes(ordered)
        label = "weekly" if meta.frequency == "weekly" else "monthly"
        if meta.frequency not in {"weekly", "monthly"}:
            label = "previous print"
        row["value"] = level
        row["mom_change"] = mom
        row["print_change"] = mom
        row["change_label"] = label
        row["avg_3_change"] = avg
    else:
        row["d1"] = _num(d1)
        row["w1"] = _num(w1)
        row["m1"] = _num(m1)
    return row


def compute_net_liquidity(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Calculate net liquidity: Fed Balance Sheet - (RRP + TGA).

    Net liquidity represents unencumbered liquidity available to markets.
    Rising net liquidity historically correlates with risk asset strength.

    Args:
        rows: Macro series rows with WALCL, RRPONTSYD, WTREGEN

    Returns:
        Dict with net_liquidity_bn, wow_change_bn, components or None if data missing
    """
    by_id = {row["series_id"]: row for row in rows}

    walcl_row = by_id.get("WALCL")
    rrp_row = by_id.get("RRPONTSYD")
    tga_row = by_id.get("WTREGEN")

    if not walcl_row or not rrp_row or not tga_row:
        return None

    fed_bs = walcl_row.get("value")
    rrp_level = rrp_row.get("value")
    tga_level = tga_row.get("value")

    if fed_bs is None or rrp_level is None or tga_level is None:
        return None

    net_liq_mn = fed_bs - rrp_level - tga_level
    net_liq_bn = net_liq_mn / 1000

    wow_change_bn = None
    if all(row.get("w1") is not None for row in (walcl_row, rrp_row, tga_row)):
        prior_net_liq = (
            (fed_bs - walcl_row["w1"]) - (rrp_level - rrp_row["w1"]) - (tga_level - tga_row["w1"])
        )
        wow_change_bn = (net_liq_mn - prior_net_liq) / 1000

    return {
        "net_liquidity_bn": round(net_liq_bn, 1),
        "wow_change_bn": round(wow_change_bn, 1) if wow_change_bn is not None else None,
        "components": {
            "fed_bs_bn": round(fed_bs / 1000, 1),
            "rrp_bn": round(rrp_level / 1000, 1),
            "tga_bn": round(tga_level / 1000, 1),
        },
    }


def named_facts(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    by_id = {row["series_id"]: row for row in rows}

    def field(series_id: str, key: str = "value") -> float | None:
        row = by_id.get(series_id)
        if row is None:
            return None
        raw = row.get(key)
        return raw if isinstance(raw, int | float) else None

    dgs2 = field("DGS2")
    dff = field("DFF")
    fed_vs_2y = None
    if dgs2 is not None and dff is not None:
        fed_vs_2y = round((dgs2 - dff) * 100, 2)
    t10y2y = field("T10Y2Y")
    return {
        "curve_2s10s": t10y2y,
        "curve_2s10s_bp": None if t10y2y is None else round(t10y2y * 100, 2),
        "curve_2s10s_w1_bp": field("T10Y2Y", "w1_bp"),
        "real_10y": field("DFII10"),
        "breakeven_10y": field("T10YIE"),
        "breakeven_5y": field("T5YIE"),
        "forward_5y5y": field("T5YIFR"),
        "fed_vs_2y_bp": fed_vs_2y,
        "dgs2": dgs2,
        "dgs2_d1_bp": field("DGS2", "d1_bp"),
        "dgs2_w1_bp": field("DGS2", "w1_bp"),
        "dgs10": field("DGS10"),
        "dgs10_w1_bp": field("DGS10", "w1_bp"),
        "dgs30": field("DGS30"),
        "dgs30_d1_bp": field("DGS30", "d1_bp"),
        "dgs30_w1_bp": field("DGS30", "w1_bp"),
    }
