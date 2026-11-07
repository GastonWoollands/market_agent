"""Opportunity sleeve scores from stored valuation + TTM + 12-1 momentum.

No vendor I/O. Form 4 is not ingested, so insider is a neutral 0.5 until that
table exists. Missing sleeves are also 0.5 (renormalize-by-neutral, not a
rescaled universe).

Weights (sum to 1.0 before risk):
  cheap    0.30  1 − own 5y EV/EBITDA percentile
  quality  0.25  rank of FCF margin and FCF yield within the sector
  change   0.20  rank of 1y EBITDA growth within the sector
  setup    0.15  rank of the 12-1 return (12 months, skipping the last) within the sector
  insider  0.10  0.5 (unavailable; omitted from the UI until Form 4)
Risk is subtracted: cheap+falling EBITDA, or high net-debt/EBITDA.
Sector-neutral ranks keep one sector's cheap year (software in 2026) from filling the
list; sectors with fewer than SECTOR_MIN_NAMES names are ranked together.
Names failing a `ScoreGate` rule (data that would rank an artifact) get no score.
The grid shows named desk metrics; these sleeves are the sort key only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from analytics.valuation import percentile_rank

WEIGHTS = {
    "cheap": 0.30,
    "quality": 0.25,
    "change": 0.20,
    "setup": 0.15,
    "insider": 0.10,
}
INSIDER_NEUTRAL = 0.5
MISSING_NEUTRAL = 0.5
CHEAP_TRAP = 0.70
LEVERAGE_CAP = 8.0
RISK_WEIGHT = 0.25
SECTOR_MIN_NAMES = 10
# One number for "the TTM is too old to price": the freshness strip uses it too.
TTM_STALE_DAYS = 150
FCF_JUMP_SHARE = 0.15
FCF_YIELD_MAX = 0.30
GROWTH_MAX = 3.0
MULTIPLE_MAX = 60.0


@dataclass(frozen=True)
class ScoreInput:
    ticker: str
    pctile_5y: float | None
    ebitda_growth_1y: float | None
    fcf_margin: float | None
    net_debt_to_ebitda: float | None
    momentum: float | None
    fcf_yield: float | None = None
    sector: str | None = None


@dataclass(frozen=True)
class ScoredName:
    ticker: str
    rank: int
    total: float
    cheap: float
    quality: float
    change: float
    setup: float
    insider: float
    risk: float
    trap: bool


def unit_ranks(values: Sequence[float | None]) -> list[float | None]:
    finite = [item for item in values if item is not None]
    if not finite:
        return [None] * len(values)
    return [None if item is None else percentile_rank(finite, item) / 100.0 for item in values]


def sector_ranks(
    values: Sequence[float | None], sectors: Sequence[str | None]
) -> list[float | None]:
    """`unit_ranks` within each sector; small or unknown sectors are ranked together."""
    sizes: dict[str | None, int] = {}
    for sector in sectors:
        sizes[sector] = sizes.get(sector, 0) + 1
    groups: dict[str | None, list[int]] = {}
    for index, sector in enumerate(sectors):
        key = sector if sector is not None and sizes[sector] >= SECTOR_MIN_NAMES else None
        groups.setdefault(key, []).append(index)
    out: list[float | None] = [None] * len(values)
    for indices in groups.values():
        for index, rank in zip(indices, unit_ranks([values[i] for i in indices]), strict=True):
            out[index] = rank
    return out


def score_universe(rows: Sequence[ScoreInput]) -> list[ScoredName]:
    sectors = [row.sector for row in rows]
    quality_m = sector_ranks([row.fcf_margin for row in rows], sectors)
    quality_y = sector_ranks([row.fcf_yield for row in rows], sectors)
    change = _fill(sector_ranks([row.ebitda_growth_1y for row in rows], sectors))
    setup = _fill(sector_ranks([row.momentum for row in rows], sectors))
    scored: list[ScoredName] = []
    for index, row in enumerate(rows):
        cheap = _cheap(row.pctile_5y)
        trap = cheap >= CHEAP_TRAP and row.ebitda_growth_1y is not None and row.ebitda_growth_1y < 0
        risk = _risk(trap, row.net_debt_to_ebitda)
        quality = _blend(quality_m[index], quality_y[index])
        total = (
            WEIGHTS["cheap"] * cheap
            + WEIGHTS["quality"] * quality
            + WEIGHTS["change"] * change[index]
            + WEIGHTS["setup"] * setup[index]
            + WEIGHTS["insider"] * INSIDER_NEUTRAL
            - RISK_WEIGHT * risk
        )
        scored.append(
            ScoredName(
                ticker=row.ticker,
                rank=0,
                total=total,
                cheap=cheap,
                quality=quality,
                change=change[index],
                setup=setup[index],
                insider=INSIDER_NEUTRAL,
                risk=risk,
                trap=trap,
            )
        )
    ordered = sorted(scored, key=lambda item: (-item.total, item.ticker))
    return [
        ScoredName(
            ticker=item.ticker,
            rank=rank,
            total=item.total,
            cheap=item.cheap,
            quality=item.quality,
            change=item.change,
            setup=item.setup,
            insider=item.insider,
            risk=item.risk,
            trap=item.trap,
        )
        for rank, item in enumerate(ordered, start=1)
    ]


def _cheap(pctile_5y: float | None) -> float:
    if pctile_5y is None:
        return MISSING_NEUTRAL
    return max(0.0, min(1.0, (100.0 - pctile_5y) / 100.0))


def _risk(trap: bool, net_debt_to_ebitda: float | None) -> float:
    leverage = 0.0
    if net_debt_to_ebitda is not None and net_debt_to_ebitda > 0:
        leverage = min(net_debt_to_ebitda / LEVERAGE_CAP, 1.0)
    trap_term = 1.0 if trap else 0.0
    return 0.6 * trap_term + 0.4 * leverage


def _fill(values: Sequence[float | None]) -> list[float]:
    return [MISSING_NEUTRAL if item is None else item for item in values]


def _blend(*values: float | None) -> float:
    parts = [item for item in values if item is not None]
    if not parts:
        return MISSING_NEUTRAL
    return sum(parts) / len(parts)


@dataclass(frozen=True)
class GateInput:
    """What the data-quality rules read for one name; ratios as fractions."""

    ticker: str
    ttm_as_of: date
    revenue: float
    fcf: float | None
    prior_fcf_low: float | None
    fcf_yield: float | None
    ebitda_growth_1y: float | None
    ev_ebitda: float | None


@dataclass(frozen=True)
class Exclusion:
    """One failed rule and the numbers behind it (stored as JSON, worded in the UI)."""

    rule: str
    values: dict[str, float | str] = field(default_factory=dict)


class ScoreGate:
    """Rules that keep data artifacts out of the ranking (they are shown, not ranked).

    fcf_one_off       FCF TTM rose from a TTM at or below zero (within the last four) by
                      more than 15% of revenue, or FCF yield above 30% (KODK, WLKP)
    base_effect       1y EBITDA change beyond ±300%: the base was near zero (AMN, SONO)
    extreme_multiple  EV/EBITDA above 60x: cheap versus its own history is not cheap
    stale_ttm         the latest TTM is more than TTM_STALE_DAYS old
    """

    def __init__(self, today: date) -> None:
        self._today = today

    def check(self, row: GateInput) -> list[Exclusion]:
        found = [
            self._fcf_one_off(row),
            self._base_effect(row),
            self._extreme_multiple(row),
            self._stale_ttm(row),
        ]
        return [item for item in found if item is not None]

    def _fcf_one_off(self, row: GateInput) -> Exclusion | None:
        if (
            row.fcf is not None
            and row.prior_fcf_low is not None
            and row.prior_fcf_low <= 0
            and row.revenue > 0
            and row.fcf - row.prior_fcf_low > FCF_JUMP_SHARE * row.revenue
        ):
            return Exclusion("fcf_one_off", {"fcf_from": row.prior_fcf_low, "fcf_to": row.fcf})
        if row.fcf_yield is not None and row.fcf_yield > FCF_YIELD_MAX:
            return Exclusion("fcf_one_off", {"fcf_yield": row.fcf_yield})
        return None

    def _base_effect(self, row: GateInput) -> Exclusion | None:
        growth = row.ebitda_growth_1y
        if growth is None or abs(growth) <= GROWTH_MAX:
            return None
        return Exclusion("base_effect", {"ebitda_growth_1y": growth})

    def _extreme_multiple(self, row: GateInput) -> Exclusion | None:
        if row.ev_ebitda is None or row.ev_ebitda <= MULTIPLE_MAX:
            return None
        return Exclusion("extreme_multiple", {"ev_ebitda": row.ev_ebitda})

    def _stale_ttm(self, row: GateInput) -> Exclusion | None:
        age = (self._today - row.ttm_as_of).days
        if age <= TTM_STALE_DAYS:
            return None
        return Exclusion("stale_ttm", {"ttm_as_of": row.ttm_as_of.isoformat(), "age_days": age})
