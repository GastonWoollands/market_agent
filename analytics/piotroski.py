"""Piotroski F-Score (0–9) from fiscal-year snapshots.

Piotroski (2000). Accrual test is CFO > net income, not CFO vs ROA.
ROA and asset turnover use beginning-of-year assets (prior year total assets).
A complete score needs three fiscal years. Incomplete tests yield f_score=None,
not zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from store.canonical import MetricFy

ZERO = Decimal("0")


@dataclass(frozen=True)
class PiotroskiResult:
    score: int | None
    tests: dict[str, Any]


def piotroski(years: list[MetricFy]) -> PiotroskiResult:
    """`years` oldest → newest. Uses the last three snapshots when present."""
    if len(years) < 2:
        return PiotroskiResult(score=None, tests={"complete": False, "reason": "need_two_years"})
    current = years[-1]
    prior = years[-2]
    prior_prior = years[-3] if len(years) >= 3 else None
    tests: dict[str, Any] = {
        "complete": True,
        "roa_base": "beginning",
        "fy_as_of": current.as_of.isoformat(),
        "prior_as_of": prior.as_of.isoformat(),
    }
    roa_now = _roa(current.net_income, prior.total_assets)
    roa_prior = (
        None
        if prior_prior is None
        else _roa(prior.net_income, prior_prior.total_assets)
    )
    turn_now = _ratio(current.revenue, prior.total_assets)
    turn_prior = (
        None if prior_prior is None else _ratio(prior.revenue, prior_prior.total_assets)
    )
    flags: dict[str, bool | None] = {
        "roa": _pos(roa_now),
        "cfo": _pos(current.cfo),
        "accrual": _gt(current.cfo, current.net_income),
        "delta_roa": _gt(roa_now, roa_prior),
        "delta_leverage": _lt(_leverage(current), _leverage(prior)),
        "delta_liquidity": _gt(_current_ratio(current), _current_ratio(prior)),
        "no_dilution": _le(current.shares, prior.shares),
        "delta_margin": _gt(_gross_margin(current), _gross_margin(prior)),
        "delta_turnover": _gt(turn_now, turn_prior),
    }
    tests.update(flags)
    if any(value is None for value in flags.values()):
        tests["complete"] = False
        return PiotroskiResult(score=None, tests=tests)
    score = sum(1 for value in flags.values() if value)
    return PiotroskiResult(score=score, tests=tests)


def _roa(net_income: Decimal | None, beginning_assets: Decimal | None) -> Decimal | None:
    return _ratio(net_income, beginning_assets)


def _leverage(row: MetricFy) -> Decimal | None:
    return _ratio(row.long_term_debt, row.total_assets)


def _current_ratio(row: MetricFy) -> Decimal | None:
    return _ratio(row.current_assets, row.current_liabilities)


def _gross_margin(row: MetricFy) -> Decimal | None:
    return _ratio(row.gross_profit, row.revenue)


def _ratio(num: Decimal | None, den: Decimal | None) -> Decimal | None:
    if num is None or den is None or den == ZERO:
        return None
    return num / den


def _pos(value: Decimal | None) -> bool | None:
    if value is None:
        return None
    return value > ZERO


def _gt(left: Decimal | None, right: Decimal | None) -> bool | None:
    if left is None or right is None:
        return None
    return left > right


def _lt(left: Decimal | None, right: Decimal | None) -> bool | None:
    if left is None or right is None:
        return None
    return left < right


def _le(left: Decimal | None, right: Decimal | None) -> bool | None:
    if left is None or right is None:
        return None
    return left <= right
