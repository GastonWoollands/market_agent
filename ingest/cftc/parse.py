from __future__ import annotations

from datetime import date
from typing import Any

from ingest.cftc.errors import CftcParseError
from store.canonical import CotReport

# Socrata column -> CotReport field. Every one is required: a missing column fails loud.
COLUMNS = {
    "open_interest_all": "open_interest",
    "dealer_positions_long_all": "dealer_long",
    "dealer_positions_short_all": "dealer_short",
    "asset_mgr_positions_long": "asset_mgr_long",
    "asset_mgr_positions_short": "asset_mgr_short",
    "lev_money_positions_long": "lev_money_long",
    "lev_money_positions_short": "lev_money_short",
}


def reports_from_rows(rows: Any) -> list[CotReport]:
    if not isinstance(rows, list):
        raise CftcParseError("TFF payload is not a list")
    return [_report(row) for row in rows if row.get("futonly_or_combined") == "FutOnly"]


def _report(row: dict[str, Any]) -> CotReport:
    try:
        code = str(row["cftc_contract_market_code"]).strip()
        day = date.fromisoformat(str(row["report_date_as_yyyy_mm_dd"])[:10])
        fields = {field: int(row[column]) for column, field in COLUMNS.items()}
    except (KeyError, ValueError) as exc:
        raise CftcParseError(f"TFF row {row.get('id')!r}: {exc}") from exc
    return CotReport(
        contract_code=code,
        report_date=day,
        market=str(row.get("market_and_exchange_names") or code),
        **fields,
    )
