"""TTM points from Yahoo quarterly statements for curated foreign filers (Phase 1.15).

Vendor data: the job stores the result with `metric_ttm.source = yahoo`, and only for
periods newer than the latest SEC point.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from store.canonical import MetricTtm, QuarterlyStatement

QUARTER_GAP_DAYS = (75, 105)
QUARTERS_PER_TTM = 4


@dataclass(frozen=True)
class StatementTtm:
    """TTM points built from consecutive quarters, or the reason none could be built."""

    points: tuple[MetricTtm, ...]
    skipped: str | None = None

    @classmethod
    def from_quarters(
        cls,
        quarters: Sequence[QuarterlyStatement],
        *,
        cik: str,
        adr_ratio: Decimal = Decimal(1),
    ) -> StatementTtm:
        if not quarters:
            return cls((), "no_quarters")
        currencies = {item.currency for item in quarters}
        if currencies != {"USD"}:
            return cls((), "non_usd")
        ordered = sorted(quarters, key=lambda item: item.period_end)
        points = tuple(
            point
            for end in range(QUARTERS_PER_TTM, len(ordered) + 1)
            if (point := _ttm(ordered[end - QUARTERS_PER_TTM : end], cik, adr_ratio)) is not None
        )
        if not points:
            return cls((), "few_quarters")
        return cls(points)


def _ttm(window: Sequence[QuarterlyStatement], cik: str, adr_ratio: Decimal) -> MetricTtm | None:
    if not _consecutive(window):
        return None
    revenue = _sum(item.revenue for item in window)
    if revenue is None:
        return None
    last = window[-1]
    ebit = _sum(item.operating_income for item in window)
    depreciation = _sum(item.depreciation for item in window)
    cfo = _sum(item.cfo for item in window)
    capex = _sum(item.capex for item in window)
    interest = _sum(item.interest_expense for item in window)
    net_debt = None
    if last.debt is not None and last.cash is not None:
        net_debt = last.debt - last.cash
    shares = None
    if last.ordinary_shares is not None and last.ordinary_shares > 0:
        shares = last.ordinary_shares / adr_ratio
    return MetricTtm(
        cik=cik,
        as_of=last.period_end,
        revenue=revenue,
        ebit=ebit,
        ebitda=None if ebit is None or depreciation is None else ebit + depreciation,
        cfo=cfo,
        capex=capex,
        fcf=None if cfo is None or capex is None else cfo - capex,
        interest_expense=None if interest is None else abs(interest),
        net_debt=net_debt,
        shares=shares,
        current_liabilities=last.current_liabilities,
        total_liabilities=last.total_liabilities,
        deferred_revenue_current=last.deferred_revenue_current,
        net_income=_sum(item.net_income for item in window),
        equity=last.equity,
    )


def _consecutive(window: Sequence[QuarterlyStatement]) -> bool:
    low, high = QUARTER_GAP_DAYS
    return all(
        low <= (later.period_end - earlier.period_end).days <= high
        for earlier, later in zip(window, window[1:], strict=False)
    )


def _sum(values) -> Decimal | None:
    """All four quarters or nothing: a TTM with a missing quarter is not a TTM."""
    items = list(values)
    if any(item is None for item in items):
        return None
    return sum(items, Decimal(0))
