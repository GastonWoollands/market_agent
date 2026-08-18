"""Opportunity sleeve scores from stored valuation + TTM + 63d returns.

No vendor I/O. Form 4 is not ingested, so insider is a neutral 0.5 until that
table exists. Missing sleeves are also 0.5 (renormalize-by-neutral, not a
rescaled universe).

Weights (sum to 1.0 before risk):
  cheap    0.30  1 − own 5y EV/EBITDA percentile
  quality  0.25  cross-section rank of FCF margin
  change   0.20  cross-section rank of 1y EBITDA growth
  setup    0.15  cross-section rank of 63-session return
  insider  0.10  0.5 (unavailable)
Risk is subtracted: cheap+falling EBITDA, or high net-debt/EBITDA.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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


@dataclass(frozen=True)
class ScoreInput:
    ticker: str
    pctile_5y: float | None
    ebitda_growth_1y: float | None
    fcf_margin: float | None
    net_debt_to_ebitda: float | None
    ret_3m: float | None


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


def score_universe(rows: Sequence[ScoreInput]) -> list[ScoredName]:
    quality = _fill(unit_ranks([row.fcf_margin for row in rows]))
    change = _fill(unit_ranks([row.ebitda_growth_1y for row in rows]))
    setup = _fill(unit_ranks([row.ret_3m for row in rows]))
    scored: list[ScoredName] = []
    for index, row in enumerate(rows):
        cheap = _cheap(row.pctile_5y)
        trap = cheap >= CHEAP_TRAP and row.ebitda_growth_1y is not None and row.ebitda_growth_1y < 0
        risk = _risk(trap, row.net_debt_to_ebitda)
        total = (
            WEIGHTS["cheap"] * cheap
            + WEIGHTS["quality"] * quality[index]
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
                quality=quality[index],
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
