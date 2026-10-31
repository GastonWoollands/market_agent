"""Named desk ratios for Valuation / Opportunities. No vendor I/O."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def fcf_yield(fcf: Decimal | float | None, ev: Decimal | float | None) -> float | None:
    return _ratio(fcf, ev, require_positive_den=True)


def nd_ebitda(net_debt: Decimal | float | None, ebitda: Decimal | float | None) -> float | None:
    return _ratio(net_debt, ebitda, require_positive_den=True)


def interest_coverage(
    ebit: Decimal | float | None, interest_expense: Decimal | float | None
) -> float | None:
    """TTM EBIT / TTM interest expense. Negative when operations lose money."""
    return _ratio(ebit, interest_expense, require_positive_den=True)


def share_change(
    shares: Decimal | float | None, shares_year_ago: Decimal | float | None
) -> float | None:
    """Share count change over a year. Positive is dilution, negative is buybacks."""
    ratio = _ratio(shares, shares_year_ago, require_positive_den=True)
    return None if ratio is None else ratio - 1.0


def financing_gap(
    capex: Decimal | float | None,
    cfo: Decimal | float | None,
    market_cap: Decimal | float | None,
) -> float | None:
    """(capex − CFO) / market cap. Positive: the name needs outside capital to invest."""
    if capex is None or cfo is None:
        return None
    return _ratio(_dec(capex) - _dec(cfo), market_cap, require_positive_den=True)


def accrual_ok(cfo: Decimal | float | None, net_income: Decimal | float | None) -> bool | None:
    if cfo is None or net_income is None:
        return None
    return _dec(cfo) > _dec(net_income)


def accrual_from_fy(row: Any | None) -> bool | None:
    if row is None:
        return None
    return accrual_ok(getattr(row, "cfo", None), getattr(row, "net_income", None))


def _ratio(
    num: Decimal | float | None,
    den: Decimal | float | None,
    *,
    require_positive_den: bool,
) -> float | None:
    if num is None or den is None:
        return None
    den_d = _dec(den)
    if den_d == 0:
        return None
    if require_positive_den and den_d <= 0:
        return None
    return float(_dec(num) / den_d)


def _dec(value: Decimal | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))
