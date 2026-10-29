"""Assemble a quant_score row (ratio snapshot + gem flag) from stored FY snapshots.

No vendor I/O. Gem flag uses catalog thresholds; insider ownership is not applied.
Piotroski / Altman are not product and are not computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from store.canonical import MetricFy
from store.catalog import GemsConfig

ZERO = Decimal("0")


@dataclass(frozen=True)
class QuantRow:
    fy_as_of: date | None
    market_cap: Decimal | None
    revenue_growth_yoy: Decimal | None
    fcf_yield: Decimal | None
    debt_to_equity: Decimal | None
    is_gem_candidate: bool


def score_quant(
    years: list[MetricFy],
    *,
    price: Decimal | None,
    shares: Decimal | None,
    fcf: Decimal | None,
    ev: Decimal | None,
    ttm_revenue: Decimal | None,
    gems: GemsConfig,
) -> QuantRow | None:
    if not years:
        return None
    current = years[-1]
    prior = years[-2] if len(years) >= 2 else None
    share_count = shares if shares is not None else current.shares
    market_cap = _mul(share_count, price)
    growth = _growth(current.revenue, None if prior is None else prior.revenue)
    fcf_yield = _ratio(fcf, ev)
    debt_to_equity = _ratio(current.long_term_debt, current.equity)
    gem = _is_gem(
        market_cap=market_cap,
        growth=growth,
        fcf_yield=fcf_yield,
        debt_to_equity=debt_to_equity,
        ttm_revenue=ttm_revenue,
        gems=gems,
    )
    return QuantRow(
        fy_as_of=current.as_of,
        market_cap=None if market_cap is None else market_cap.quantize(Decimal("0.01")),
        revenue_growth_yoy=growth,
        fcf_yield=fcf_yield,
        debt_to_equity=debt_to_equity,
        is_gem_candidate=gem,
    )


def _is_gem(
    *,
    market_cap: Decimal | None,
    growth: Decimal | None,
    fcf_yield: Decimal | None,
    debt_to_equity: Decimal | None,
    ttm_revenue: Decimal | None,
    gems: GemsConfig,
) -> bool:
    lo = Decimal(gems.min_market_cap_usd)
    hi = Decimal(gems.max_market_cap_usd)
    if market_cap is None or market_cap < lo or market_cap > hi:
        return False
    if ttm_revenue is not None and ttm_revenue < Decimal(gems.min_revenue_usd):
        return False
    if growth is None or growth <= Decimal(str(gems.min_revenue_growth_yoy)):
        return False
    if fcf_yield is None or fcf_yield <= Decimal(str(gems.min_fcf_yield)):
        return False
    if debt_to_equity is None or debt_to_equity >= Decimal(str(gems.max_debt_to_equity)):
        return False
    return True


def _growth(now: Decimal | None, prior: Decimal | None) -> Decimal | None:
    if now is None or prior is None or prior <= ZERO:
        return None
    return (now / prior) - 1


def _ratio(num: Decimal | None, den: Decimal | None) -> Decimal | None:
    if num is None or den is None or den == ZERO:
        return None
    return num / den


def _mul(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left * right
