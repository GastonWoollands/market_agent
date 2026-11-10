"""FOMC reads for the pack: the latest SEP (dot plot summary) and the latest decision vote.

SEP: FRED publishes the Summary of Economic Projections as series dated by projection
year (2026-01-01 = year-end 2026) and rewrites them on every release; the longer-run
median is dated by the release itself, so it carries the SEP date. Storage keeps only
the current release (ingest replaces SEP series), so a pack dated before that release
gets no SEP rather than a later one. Dots are anonymous: there is no per-participant view.

Vote: parsed from the stored FOMC statement text (`policy_item.excerpt`). Only rate
decision statements count. The statement gives the tally ("by a 10 – 2 vote"), sometimes
the voters, and each dissenting group with its preferred action.
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
MOVE_BP = Decimal(25)


def _num(value: Decimal | None, ndigits: int = 2) -> float | None:
    return None if value is None else round(float(value), ndigits)


@dataclass(frozen=True)
class SepSnapshot:
    """Latest SEP by projection year, plus the funds-rate dispersion (Decimal inside)."""

    as_of: date
    blocks: dict[str, dict[str, dict[int, Decimal]]]
    longer_run_median: Decimal | None

    @classmethod
    def from_points(cls, points: Mapping[str, Points], *, as_of: date) -> SepSnapshot | None:
        """None when no release is stored or the latest release is after `as_of`."""
        longer = sorted(points.get(LONGER_RUN_ID) or [])
        if not longer:
            return None
        released, longer_value = longer[-1]
        if released > as_of:
            return None
        blocks: dict[str, dict[str, dict[int, Decimal]]] = {}
        for series_id, (block, field) in SEP_FIELDS.items():
            by_year = {
                day.year: value
                for day, value in sorted(points.get(series_id) or [])
                if day.year >= released.year and value is not None
            }
            if by_year:
                blocks.setdefault(block, {})[field] = by_year
        if not blocks:
            return None
        return cls(as_of=released, blocks=blocks, longer_run_median=longer_value)

    def median_funds(self, year: int) -> Decimal | None:
        return self.blocks.get("fed_funds", {}).get("median", {}).get(year)

    def to_pack(self, *, as_of: date, dff: Decimal | None) -> dict[str, Any]:
        """Writer-facing dict. Gaps and move counts are precomputed: the writer never computes."""
        current = self.median_funds(as_of.year)
        following = self.median_funds(as_of.year + 1)
        gap = None if current is None or dff is None else (current - dff) * 100
        step = None if current is None or following is None else (following - current) * 100
        out: dict[str, Any] = {
            "as_of": self.as_of.isoformat(),
            "note": "SEP medians of year-end projections; dots are anonymous.",
        }
        for block, fields in self.blocks.items():
            out[block] = {
                field: {str(year): _num(value) for year, value in years.items()}
                for field, years in fields.items()
            }
        out.update(
            {
                "fed_funds_longer_run_median": _num(self.longer_run_median),
                "current_year": str(as_of.year),
                "median_current_year": _num(current),
                "next_year": str(as_of.year + 1),
                "median_next_year": _num(following),
                "median_vs_dff_bp": _num(gap, 1),
                "implied_25bp_moves_current_year": _num(None if gap is None else gap / MOVE_BP, 1),
                "median_next_vs_current_bp": _num(step, 1),
            }
        )
        return out


# A sentence ends at a period that is not a middle initial ("Lisa D. Cook").
_END = r"(?<!\s[A-Z])\.(?=\s|$)"
_TALLY_RE = re.compile(r"by an? (\d+)\s*[–—-]\s*(\d+) vote", re.IGNORECASE)
_UNANIMOUS_RE = re.compile(r"\bunanimous", re.IGNORECASE)
_DECISION_RE = re.compile(
    r"decided to (maintain|raise|lower) the target range for the federal funds rate"
    r"(?: by [^,]+?)? (?:at|to) ([\d\-/]+ to [\d\-/]+) percent",
    re.IGNORECASE,
)
_ACTION = r"(?:the monetary policy |this |the )?action"
_FOR_RE = re.compile(rf"Voting for {_ACTION} were:?\s*(.+?){_END}", re.IGNORECASE)
_AGAINST_RE = re.compile(rf"Voting against {_ACTION} (?:was|were)\s+", re.IGNORECASE)
_PREFERRED_RE = re.compile(r",?\s*who preferred\s+", re.IGNORECASE)
# Between one group's preference and the next group's names: "; and", "; " or ", and Name".
_GROUP_SEP_RE = re.compile(r";\s*(?:and\s+)?|,\s+and\s+(?=[A-Z])")
_ROLES = frozenset({"Chair", "Vice Chair"})


def _names(raw: str) -> list[str]:
    parts = re.split(r"[;,]\s*(?:and\s+)?|\s+and\s+", raw.strip().rstrip(";:."))
    # Drop role labels that follow a name ("Jerome H. Powell, Chair").
    return [part.strip() for part in parts if part.strip() and part.strip() not in _ROLES]


def _direction(preference: str) -> str | None:
    lowered = preference.lower()
    if "no change" in lowered or "maintain" in lowered or "keep" in lowered:
        return "hold"
    if "lower" in lowered or "reduce" in lowered or "cut" in lowered:
        return "cut"
    if "raise" in lowered or "increase" in lowered:
        return "hike"
    return None


def _first_sentence(text: str) -> str:
    match = re.search(_END, text)
    return text[: match.start()] if match else text


@dataclass(frozen=True)
class Dissent:
    name: str
    preferred: str | None
    direction: str | None


def _dissents(text: str) -> tuple[Dissent, ...] | None:
    """Each dissenting group with its own preference; None when there is no dissent line."""
    found = _AGAINST_RE.search(text)
    if found is None:
        return None
    pieces = _PREFERRED_RE.split(text[found.end() :])
    if len(pieces) == 1:
        return tuple(Dissent(name, None, None) for name in _names(_first_sentence(pieces[0])))
    out: list[Dissent] = []
    names = pieces[0]
    for index, chunk in enumerate(pieces[1:], start=1):
        last = index == len(pieces) - 1
        if last:
            preference, following = _first_sentence(chunk), ""
        else:
            splits = list(_GROUP_SEP_RE.finditer(chunk))
            cut = splits[-1] if splits else None
            preference = chunk[: cut.start()] if cut else chunk
            following = chunk[cut.end() :] if cut else ""
        preference = preference.strip().rstrip(".;,")
        out.extend(Dissent(name, preference, _direction(preference)) for name in _names(names))
        names = following
    return tuple(out)


@dataclass(frozen=True)
class FomcVote:
    """Tally and dissents of the latest FOMC rate decision, from the statement text."""

    date: date
    url: str | None
    decision: str | None
    target_range: str | None
    votes_for: int | None
    votes_against: int | None
    unanimous: bool | None
    dissents: tuple[Dissent, ...]
    voters_for: tuple[str, ...]
    complete: bool

    @classmethod
    def parse(cls, text: str | None, *, published: date, url: str | None) -> FomcVote | None:
        """None unless the text is a rate decision statement."""
        if not text:
            return None
        decision = _DECISION_RE.search(text)
        if decision is None:
            return None
        tally = _TALLY_RE.search(text)
        voters = _FOR_RE.search(text)
        voters_for = tuple(_names(voters.group(1))) if voters else ()
        dissents = _dissents(text) or ()
        votes_for = int(tally.group(1)) if tally else (len(voters_for) or None)
        if tally:
            votes_against: int | None = int(tally.group(2))
        elif dissents:
            votes_against = len(dissents)
        elif voters_for or _UNANIMOUS_RE.search(text):
            votes_against = 0
        else:
            votes_against = None
        unanimous = None if votes_against is None else votes_against == 0
        # Truncated bodies can keep the tally but lose the dissent names.
        complete = votes_against is not None and len(dissents) == votes_against
        return cls(
            date=published,
            url=url,
            decision=decision.group(1).lower(),
            target_range=decision.group(2).strip(),
            votes_for=votes_for,
            votes_against=votes_against,
            unanimous=unanimous,
            dissents=dissents,
            voters_for=voters_for,
            complete=complete,
        )

    @classmethod
    def latest(cls, statements: Sequence[Any]) -> FomcVote | None:
        """Newest rate decision statement; title-only and non-decision items are skipped."""
        ordered = sorted(statements, key=lambda item: item.published_at, reverse=True)
        for item in ordered:
            published = item.published_at
            day = published.date() if isinstance(published, datetime) else published
            vote = cls.parse(item.excerpt, published=day, url=item.url)
            if vote is not None:
                return vote
        return None

    def to_pack(self) -> dict[str, Any]:
        directions = {item.direction for item in self.dissents if item.direction}
        return {
            "date": self.date.isoformat(),
            "url": self.url,
            "decision": self.decision,
            "target_range": self.target_range,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "unanimous": self.unanimous,
            "dissents": [
                {"name": item.name, "preferred": item.preferred, "direction": item.direction}
                for item in self.dissents
            ],
            "dissent_direction": (
                None if not directions else directions.pop() if len(directions) == 1 else "mixed"
            ),
            "voters_for": list(self.voters_for) or None,
            "complete": self.complete,
        }
