from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.finra.errors import FinraParseError
from store.canonical import ShortInterestReport

FIELDS = (
    "symbolCode",
    "settlementDate",
    "currentShortPositionQuantity",
    "previousShortPositionQuantity",
    "averageDailyVolumeQuantity",
    "daysToCoverQuantity",
    "changePercent",
)


def finra_symbol(ticker: str) -> str:
    """Our ticker -> FINRA symbol: class shares drop the separator (BRK-B -> BRKB)."""
    return "".join(char for char in ticker.upper() if char.isalnum())


def reports_from_rows(rows: Any) -> list[ShortInterestReport]:
    if not isinstance(rows, list):
        raise FinraParseError("short interest payload is not a list")
    return [_report(row) for row in rows]


def settlement_dates(rows: Any) -> list[date]:
    if not isinstance(rows, list):
        raise FinraParseError("settlement date payload is not a list")
    return sorted({_date(row) for row in rows})


def _report(row: Any) -> ShortInterestReport:
    if not isinstance(row, dict):
        raise FinraParseError("short interest row is not an object")
    try:
        return ShortInterestReport(
            symbol=str(row["symbolCode"]),
            settlement_date=_date(row),
            short_shares=int(row["currentShortPositionQuantity"]),
            prev_short_shares=_int(row.get("previousShortPositionQuantity")),
            avg_daily_volume=_int(row.get("averageDailyVolumeQuantity")),
            days_to_cover=_dec(row.get("daysToCoverQuantity")),
            change_pct=_dec(row.get("changePercent")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FinraParseError(f"short interest row {row.get('symbolCode')!r}: {exc}") from exc


def _date(row: dict[str, Any]) -> date:
    try:
        return date.fromisoformat(str(row["settlementDate"])[:10])
    except (KeyError, ValueError) as exc:
        raise FinraParseError(f"bad settlementDate in {row!r}") from exc


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise FinraParseError(f"not a number: {value!r}") from exc
