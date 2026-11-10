"""FOMC reads for the pack: the latest SEP (dot plot summary) and the latest decision vote.

SEP: FRED publishes the Summary of Economic Projections as series dated by projection
year (2026-01-01 = year-end 2026) and rewrites them on every release; the longer-run
median is dated by the release itself, so it carries the SEP date. Dots are anonymous:
there is no per-participant projection to show.

Vote: parsed from the stored FOMC statement text (`policy_item.excerpt`), which states the
tally ("by a 10 – 2 vote") and names any dissenters with their preferred action.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

Points = Sequence[tuple[date, Decimal]]

LONGER_RUN_ID = "FEDTARMDLR"
# series id -> (block, field) in the packed `sep` object
SEP_FIELDS: dict[str, tuple[str, str]] = {
    "FEDTARMD": ("fed_funds", "median"),
    "FEDTARRH": ("fed_funds", "range_high"),
    "FEDTARRL": ("fed_funds", "range_low"),
    "FEDTARCTH": ("fed_funds", "central_tendency_high"),
    "FEDTARCTL": ("fed_funds", "central_tendency_low"),
    "GDPC1MD": ("gdp_growth", "median"),
    "UNRATEMD": ("unemployment", "median"),
    "PCECTPIMD": ("pce_inflation", "median"),
    "JCXFEMD": ("core_pce_inflation", "median"),
}


def _num(value: Decimal | float | None, ndigits: int = 2) -> float | None:
    return None if value is None else round(float(value), ndigits)


@dataclass(frozen=True)
class SepSnapshot:
    """Latest SEP medians by projection year, plus the funds-rate dispersion."""

    as_of: date
    blocks: dict[str, dict[str, dict[str, float]]]
    longer_run_median: float | None

    @classmethod
    def from_points(cls, points: Mapping[str, Points]) -> SepSnapshot | None:
        longer = sorted(points.get(LONGER_RUN_ID) or [])
        if not longer:
            return None
        as_of, longer_value = longer[-1]
        blocks: dict[str, dict[str, dict[str, float]]] = {}
        for series_id, (block, field) in SEP_FIELDS.items():
            by_year = {
                str(day.year): _num(value)
                for day, value in sorted(points.get(series_id) or [])
                # Older vintages can leave past projection years in storage.
                if day.year >= as_of.year and value is not None
            }
            if by_year:
                blocks.setdefault(block, {})[field] = by_year
        if not blocks:
            return None
        return cls(as_of=as_of, blocks=blocks, longer_run_median=_num(longer_value))

    def median_funds(self, year: int) -> float | None:
        return self.blocks.get("fed_funds", {}).get("median", {}).get(str(year))

    def to_pack(self, *, as_of: date, dff: float | None) -> dict[str, Any]:
        """Writer-facing dict. `median_vs_dff_bp` is precomputed: the writer never subtracts."""
        current = self.median_funds(as_of.year)
        gap = None if current is None or dff is None else round((current - dff) * 100, 1)
        out: dict[str, Any] = {
            "as_of": self.as_of.isoformat(),
            "note": "SEP medians of year-end projections; dots are anonymous.",
            **self.blocks,
            "fed_funds_longer_run_median": self.longer_run_median,
            "current_year": str(as_of.year),
            "median_current_year": current,
            "median_vs_dff_bp": gap,
        }
        return out


_TALLY_RE = re.compile(r"by an? (\d+)\s*[–—-]\s*(\d+) vote", re.IGNORECASE)
_UNANIMOUS_RE = re.compile(r"\bunanimous", re.IGNORECASE)
# A sentence ends at a period that is not a middle initial ("Lisa D. Cook").
_END = r"(?<!\s[A-Z])\.(?:\s|$)"
_DECISION_RE = re.compile(
    r"decided to (maintain|raise|lower) the target range for the federal funds rate"
    r"(?: by [^,]+?)? (?:at|to) ([\d\-/]+ to [\d\-/]+) percent",
    re.IGNORECASE,
)
_FOR_RE = re.compile(r"Voting for (?:the monetary policy|this) action were:?\s*(.+?)" + _END, re.I)
_AGAINST_RE = re.compile(
    r"Voting against (?:the monetary policy |this )?action (?:was|were) (.+?)"
    r"(?:, who preferred to (.+?))?" + _END,
    re.IGNORECASE,
)
_ROLES = frozenset({"Chair", "Vice Chair"})
_PREFER_DIRECTION = (("raise", "hike"), ("lower", "cut"), ("maintain", "hold"))


def _names(raw: str) -> list[str]:
    parts = re.split(r"[;,]\s*(?:and\s+)?|\s+and\s+", raw.strip().rstrip(";:"))
    # Drop role labels that follow a name ("Jerome H. Powell, Chair").
    return [part.strip() for part in parts if part.strip() and part.strip() not in _ROLES]


@dataclass(frozen=True)
class FomcVote:
    """Tally and dissents of the latest FOMC decision, from the statement text."""

    date: date
    url: str | None
    decision: str | None
    target_range: str | None
    votes_for: int | None
    votes_against: int | None
    unanimous: bool
    dissenters: tuple[str, ...]
    dissent_preference: str | None
    dissent_direction: str | None
    voters_for: tuple[str, ...]

    @classmethod
    def parse(cls, text: str | None, *, published: date, url: str | None) -> FomcVote | None:
        if not text:
            return None
        tally = _TALLY_RE.search(text)
        against = _AGAINST_RE.search(text)
        unanimous = bool(_UNANIMOUS_RE.search(text)) and against is None
        if tally is None and against is None and not unanimous:
            return None
        decision = _DECISION_RE.search(text)
        voters = _FOR_RE.search(text)
        preference = against.group(2).strip() if against and against.group(2) else None
        direction = None
        if preference:
            lowered = preference.lower()
            direction = next((tag for verb, tag in _PREFER_DIRECTION if verb in lowered), None)
        return cls(
            date=published,
            url=url,
            decision=decision.group(1).lower() if decision else None,
            target_range=decision.group(2).strip() if decision else None,
            votes_for=int(tally.group(1)) if tally else None,
            votes_against=int(tally.group(2)) if tally else (0 if unanimous else None),
            unanimous=unanimous,
            dissenters=tuple(_names(against.group(1))) if against else (),
            dissent_preference=preference,
            dissent_direction=direction,
            voters_for=tuple(_names(voters.group(1))) if voters else (),
        )

    @classmethod
    def latest(cls, statements: Sequence[Any]) -> FomcVote | None:
        """First parsable statement, newest first (title-only rows are skipped)."""
        ordered = sorted(statements, key=lambda item: item.published_at, reverse=True)
        for item in ordered:
            published = item.published_at
            day = published.date() if isinstance(published, datetime) else published
            vote = cls.parse(item.excerpt, published=day, url=item.url)
            if vote is not None:
                return vote
        return None

    def to_pack(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "url": self.url,
            "decision": self.decision,
            "target_range": self.target_range,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "unanimous": self.unanimous,
            "dissenters": list(self.dissenters),
            "dissent_preference": self.dissent_preference,
            "dissent_direction": self.dissent_direction,
            "voters_for": list(self.voters_for) or None,
        }
