"""Put SEC share counts on the split basis of Yahoo's closes. No vendor calls, no DB.

Yahoo closes are split-adjusted to today's share basis. SEC share counts are as reported, so a
TTM row filed before a 5:1 split carries one fifth of today's shares, and price x shares
understates market cap 5x for every day priced off that row.

Yahoo says a split of ratio r happened on date d. The share series says where the basis
changes, because SEC counts do not switch on d itself:

- restated early: a filing that closes before d but is issued after it already shows the new
  count (SAB Topic 4C); a late filer can be two rows early (SMCI).
- lagged: the count is the cover-page figure of the prior filing, so the jump shows one row
  after d (NVDA, CMG).

For each split, oldest first, find the adjacent TTM pair whose share ratio is r (within
TOLERANCE), trying the pair straddling d, one row earlier, one row later, two rows earlier.
Scale every row before that pair. Without a jump:

- no row on or after d, or only one (the jump may still be lagged): the split is newer than
  the stored counts, so scale all rows.
- more rows after d: the series is already consistent. Scale nothing and log it.

Ratios near 1 are Yahoo spin-off adjustments (HON 1.061): there is no jump to find, and Yahoo
scaled the closes before d, so the rows before d are scaled by date.

Only adjacent rows are compared: buybacks and dilution drift too much over years.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

log = logging.getLogger(__name__)

# BKNG 25:1 shows as 24.47 and ORLY 15:1 as 14.89 in reported counts.
TOLERANCE = 0.10
# Boundary offsets from the first row on or after the split, most likely first.
CANDIDATES = ((0, "straddle"), (-1, "restated_early"), (1, "lagged"), (-2, "restated_early"))


@dataclass(frozen=True)
class Split:
    day: date
    ratio: float


@dataclass(frozen=True)
class SplitMatch:
    """How one split was applied: rows before `boundary` were scaled (None = none scaled)."""

    split: Split
    boundary: int | None
    rule: str


class ShareBasis:
    """Maps reported share counts onto the current (post-split) basis."""

    def __init__(
        self,
        splits: Sequence[tuple[date, Decimal | float]],
        *,
        tolerance: float = TOLERANCE,
    ) -> None:
        self._splits = sorted(
            (Split(day, float(ratio)) for day, ratio in splits if ratio and float(ratio) > 0),
            key=lambda item: item.day,
        )
        self._splits = [item for item in self._splits if item.ratio != 1.0]
        self._log_tolerance = math.log1p(tolerance)

    @property
    def splits(self) -> list[Split]:
        return list(self._splits)

    def factors(self, rows: Sequence[tuple[date, float]]) -> list[float]:
        """Multiplier per row (rows sorted by as_of). 1.0 when no split applies."""
        factors, _matches = self.explain(rows)
        return factors

    def adjust(self, rows: Sequence[tuple[date, float]]) -> list[float]:
        factors = self.factors(rows)
        return [shares * factor for (_day, shares), factor in zip(rows, factors, strict=True)]

    def explain(self, rows: Sequence[tuple[date, float]]) -> tuple[list[float], list[SplitMatch]]:
        if any(rows[i][0] > rows[i + 1][0] for i in range(len(rows) - 1)):
            raise ValueError("rows must be sorted by as_of")
        factors = [1.0] * len(rows)
        matches: list[SplitMatch] = []
        if not rows:
            return factors, matches
        for split in self._splits:
            match = self._place(split, rows)
            matches.append(match)
            if match.boundary is None:
                if match.rule == "unmatched":
                    log.info(
                        "split %s x%s: no share jump next to it; stored counts left as reported",
                        split.day,
                        split.ratio,
                    )
                continue
            for index in range(match.boundary):
                factors[index] *= split.ratio
        return factors, matches

    def _place(self, split: Split, rows: Sequence[tuple[date, float]]) -> SplitMatch:
        last = len(rows) - 1
        # Index of the first row on or after the split; len(rows) when every row is older.
        anchor = next((i for i, (day, _shares) in enumerate(rows) if day >= split.day), len(rows))
        if self._is_adjustment(split.ratio):
            return SplitMatch(split, anchor, "date")
        for offset, rule in CANDIDATES:
            boundary = anchor + offset
            if 1 <= boundary <= last and self._is_jump(
                rows[boundary - 1][1], rows[boundary][1], split.ratio
            ):
                return SplitMatch(split, boundary, rule)
        if anchor == len(rows):
            return SplitMatch(split, len(rows), "after_last_filing")
        if anchor == 0:
            return SplitMatch(split, None, "before_history")
        if anchor == last:
            return SplitMatch(split, len(rows), "pending_lag")
        return SplitMatch(split, None, "unmatched")

    def _is_adjustment(self, ratio: float) -> bool:
        return abs(math.log(ratio)) < 2 * self._log_tolerance

    def _is_jump(self, before: float, after: float, ratio: float) -> bool:
        if before <= 0 or after <= 0:
            return False
        return abs(math.log(after / before) - math.log(ratio)) <= self._log_tolerance
