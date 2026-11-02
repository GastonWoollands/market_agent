from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.cboe.errors import CboeParseError
from store.canonical import CboeProductStat

# product → (ratio name, section name) in the daily JSON. Any missing key fails the parse:
# Cboe changing the file must be loud, not a silent NULL.
PRODUCTS: dict[str, tuple[str, str]] = {
    "total": ("TOTAL PUT/CALL RATIO", "SUM OF ALL PRODUCTS"),
    "index": ("INDEX PUT/CALL RATIO", "INDEX OPTIONS"),
    "etp": ("EXCHANGE TRADED PRODUCTS PUT/CALL RATIO", "EXCHANGE TRADED PRODUCTS"),
    "equity": ("EQUITY PUT/CALL RATIO", "EQUITY OPTIONS"),
    "vix": ("CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO", "CBOE VOLATILITY INDEX (VIX)"),
    "spx": ("SPX + SPXW PUT/CALL RATIO", "SPX + SPXW"),
}


def stats_from_payload(as_of: date, payload: Any) -> list[CboeProductStat]:
    if not isinstance(payload, dict):
        raise CboeParseError(f"{as_of}: payload is not an object")
    ratios = payload.get("ratios")
    if not isinstance(ratios, list):
        raise CboeParseError(f"{as_of}: ratios missing")
    by_name = {row.get("name"): row.get("value") for row in ratios if isinstance(row, dict)}
    out: list[CboeProductStat] = []
    for product, (ratio_name, section_name) in PRODUCTS.items():
        if ratio_name not in by_name:
            raise CboeParseError(f"{as_of}: ratio {ratio_name!r} missing")
        section = payload.get(section_name)
        if not isinstance(section, list):
            raise CboeParseError(f"{as_of}: section {section_name!r} missing")
        rows = {row.get("name"): row for row in section if isinstance(row, dict)}
        volume, interest = rows.get("VOLUME"), rows.get("OPEN INTEREST")
        if volume is None or interest is None:
            raise CboeParseError(f"{as_of}: {section_name!r} lacks volume or open interest")
        out.append(
            CboeProductStat(
                as_of=as_of,
                product=product,
                pc_ratio=_ratio(by_name[ratio_name]),
                call_volume=_count(volume, "call", as_of),
                put_volume=_count(volume, "put", as_of),
                call_oi=_count(interest, "call", as_of),
                put_oi=_count(interest, "put", as_of),
            )
        )
    return out


def _ratio(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _count(row: dict[str, Any], key: str, as_of: date) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CboeParseError(f"{as_of}: {row.get('name')} {key} is not an integer")
    return value
