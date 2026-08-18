from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.fred.errors import FredParseError
from store.canonical import MacroPoint


def observations_from_payload(series_id: str, payload: dict[str, Any]) -> list[MacroPoint]:
    if payload.get("error_code"):
        message = str(payload.get("error_message") or payload["error_code"])
        raise FredParseError(f"{series_id}: {message}")
    rows = payload.get("observations")
    if not isinstance(rows, list):
        raise FredParseError(f"{series_id}: observations missing")

    points: list[MacroPoint] = []
    seen: set[date] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_value = row.get("value")
        if raw_value in (None, ".", ""):
            continue
        try:
            value = Decimal(str(raw_value))
        except (InvalidOperation, ValueError):
            continue
        try:
            session_date = date.fromisoformat(str(row.get("date", ""))[:10])
        except ValueError:
            continue
        if session_date in seen:
            continue
        seen.add(session_date)
        points.append(MacroPoint(series_id=series_id, date=session_date, value=value))
    if not points:
        raise FredParseError(f"{series_id}: no usable observations")
    return points
