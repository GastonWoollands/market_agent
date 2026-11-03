"""Kalshi on Live: index close ranges and the second-venue price on a Polymarket row.

Reads `odds_snapshot` rows with source = kalshi; nothing is fetched here.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from api.schemas import LiveOdds, LiveOddsAlt, LiveRange
from store.catalog import KalshiFile, KalshiSeries

NO_OPEN_RANGE = "No open range market."
_MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November"
    r"|December) (\d{4})\b",
    re.IGNORECASE,
)
_FED_MOVE = re.compile(r"\b(increase|hike|decrease|cut)\D{0,30}?(\d+)\s*(\+)?\s*bps")


def fed_outcome_key(text: str) -> str | None:
    """Polymarket Fed question -> the outcome key used in kalshi_series.yaml."""
    lowered = text.lower()
    if "no change" in lowered or "maintain" in lowered:
        return "hold"
    match = _FED_MOVE.search(lowered)
    if match is None:
        return None
    direction = "hike" if match[1] in ("increase", "hike") else "cut"
    size = 50 if match[3] or int(match[2]) > 25 else 25
    return f"{direction}_{size}"


class KalshiLiveView:
    """Stored Kalshi rows shaped for Live, keyed by catalog slot."""

    def __init__(
        self, rows: Sequence[Any], catalog: KalshiFile, *, now: datetime | None = None
    ) -> None:
        self._rows = {row.slot: row for row in rows}
        self._catalog = catalog
        self._now = now or datetime.now(UTC)

    def ranges(self) -> list[LiveRange]:
        return [self._range(series) for series in self._catalog.by_kind("range")]

    def with_alt(self, items: Sequence[LiveOdds]) -> list[LiveOdds]:
        paired = self._catalog.paired()
        return [
            item.model_copy(update={"alt": self._alt(paired[item.slot], item)})
            if item.slot in paired
            else item
            for item in items
        ]

    def _range(self, series: KalshiSeries) -> LiveRange:
        row = self._rows.get(series.slot)
        raw = (row.raw or {}) if row is not None else {}
        close_at = _time(raw.get("strike_date"))
        if row is None or close_at is None or close_at <= self._now:
            return LiveRange(slot=series.slot, label=series.label, unavailable=NO_OPEN_RANGE)
        return LiveRange(
            slot=series.slot,
            label=series.label,
            close_at=close_at,
            p10=raw.get("p10"),
            p50=raw.get("p50"),
            p90=raw.get("p90"),
            thin=bool(raw.get("thin")),
            as_of=row.as_of,
        )

    def _alt(self, series: KalshiSeries, item: LiveOdds) -> LiveOddsAlt | None:
        row = self._rows.get(series.slot)
        if row is None:
            return None
        raw = row.raw or {}
        close_at = _time(raw.get("strike_date"))
        if close_at is not None and close_at <= self._now:
            return None
        if series.kind == "binary":
            yes = float(row.implied_yes)
        else:
            yes = self._matching_outcome(raw, item, close_at)
            if yes is None:
                return None
        return LiveOddsAlt(
            source="kalshi",
            implied_yes=yes,
            question=row.question,
            thin=bool(raw.get("thin")),
        )

    @staticmethod
    def _matching_outcome(
        raw: dict[str, Any], item: LiveOdds, close_at: datetime | None
    ) -> float | None:
        """Kalshi price of the outcome Polymarket ranks first, at the same meeting."""
        if not item.outcomes:
            return None
        top = item.outcomes[0].label
        meeting = _MONTH_YEAR.search(top)
        if (
            meeting
            and close_at
            and close_at.strftime("%B %Y").lower() != " ".join(meeting.groups()).lower()
        ):
            return None
        key = fed_outcome_key(top)
        for market in raw.get("markets") or []:
            if market.get("key") == key:
                return None if market.get("yes") is None else float(market["yes"])
        return None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value)
