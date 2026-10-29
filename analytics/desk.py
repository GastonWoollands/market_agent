"""Named desk ratios for Valuation / Opportunities. No vendor I/O."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def fcf_yield(fcf: Decimal | float | None, ev: Decimal | float | None) -> float | None:
    return _ratio(fcf, ev, require_positive_den=True)


def nd_ebitda(net_debt: Decimal | float | None, ebitda: Decimal | float | None) -> float | None:
    return _ratio(net_debt, ebitda, require_positive_den=True)


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
