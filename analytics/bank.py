"""Bank read (Phase 1.15): P/E, P/B, ROE where EV/EBITDA does not apply.

Inputs are stored TTM rows (`metric_ttm.net_income`, `metric_ttm.equity`) and the latest
close. Not a sleeve and not a rank input.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

# ROE averages equity now and about a year earlier; a nearer row is not a year.
YEAR_AGO_DAYS = (300, 430)


@dataclass(frozen=True)
class BankRead:
    ttm_as_of: date
    source: str
    market_cap: float | None
    net_income: float | None
    equity: float | None
    pe: float | None
    pb: float | None
    roe: float | None
    roe_basis: str | None  # "average" (now and a year ago) or "ending" (latest equity only)

    @classmethod
    def from_ttm(cls, rows: Sequence[Any], close: float | None) -> BankRead | None:
        """`rows` are TTM rows oldest first; `close` is the latest ADR close."""
        if not rows:
            return None
        latest = rows[-1]
        income = _num(latest.net_income)
        equity = _num(latest.equity)
        shares = _num(latest.shares)
        market_cap = close * shares if close and shares else None
        prior = _year_ago(rows)
        prior_equity = _num(getattr(prior, "equity", None))
        roe, basis = None, None
        if income is not None and equity and equity > 0:
            if prior_equity and prior_equity > 0:
                roe, basis = income / ((equity + prior_equity) / 2), "average"
            else:
                roe, basis = income / equity, "ending"
        return cls(
            ttm_as_of=latest.as_of,
            source=str(getattr(latest, "source", "sec")),
            market_cap=market_cap,
            net_income=income,
            equity=equity,
            pe=market_cap / income if market_cap and income and income > 0 else None,
            pb=market_cap / equity if market_cap and equity and equity > 0 else None,
            roe=roe,
            roe_basis=basis,
        )


def _year_ago(rows: Sequence[Any]) -> Any | None:
    latest = rows[-1].as_of
    low, high = YEAR_AGO_DAYS
    candidates = [row for row in rows[:-1] if low <= (latest - row.as_of).days <= high]
    return candidates[-1] if candidates else None


def _num(value: Any) -> float | None:
    return None if value is None else float(value)
