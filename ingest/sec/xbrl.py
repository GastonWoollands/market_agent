"""Readers for raw companyfacts rows, shared by the TTM, FY and share-count parsers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def unit_rows(
    facts: dict[str, Any], taxonomy: str, concept: str, units: tuple[str, ...]
) -> list[dict[str, Any]]:
    node = facts.get(taxonomy)
    if not isinstance(node, dict):
        return []
    concept_node = node.get(concept)
    if not isinstance(concept_node, dict):
        return []
    unit_map = concept_node.get("units")
    if not isinstance(unit_map, dict):
        return []
    rows: list[dict[str, Any]] = []
    for unit in units:
        raw = unit_map.get(unit)
        if isinstance(raw, list):
            rows.extend(item for item in raw if isinstance(item, dict))
    return rows


def as_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
