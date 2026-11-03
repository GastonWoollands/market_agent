"""Short interest and street EPS revisions, read for one name.

Short interest is shown against shares outstanding (SEC), not float: float is not stored,
and for founder- or parent-controlled names the float share would be higher.
Revisions use the change in the consensus EPS and the count of analysts moving it; the
change is scaled by |prior| so a loss that narrows reads as an upward revision.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

# Yahoo earningsTrend periods shown, in order: current fiscal year, next fiscal year.
FISCAL_YEARS = (("0y", "Current fiscal year"), ("+1y", "Next fiscal year"))


class ShortRow(Protocol):
    settlement_date: date
    short_shares: int
    days_to_cover: Decimal | None
    change_pct: Decimal | None


class RevisionRow(Protocol):
    as_of: date
    period: str
    eps_current: Decimal | None
    eps_30d: Decimal | None
    eps_90d: Decimal | None
    up_30d: int | None
    down_30d: int | None


@dataclass(frozen=True)
class ShortInterestRead:
    settlement_date: date
    short_shares: int
    share_of_outstanding: float | None
    days_to_cover: float | None
    change: float | None

    @classmethod
    def from_row(cls, row: ShortRow, shares_outstanding: Decimal | None) -> ShortInterestRead:
        share = (
            row.short_shares / float(shares_outstanding)
            if shares_outstanding is not None and shares_outstanding > 0
            else None
        )
        return cls(
            settlement_date=row.settlement_date,
            short_shares=row.short_shares,
            share_of_outstanding=share,
            days_to_cover=_float(row.days_to_cover),
            change=None if row.change_pct is None else float(row.change_pct) / 100,
        )


@dataclass(frozen=True)
class RevisionRead:
    period: str
    label: str
    eps: float | None
    change_30d: float | None
    change_90d: float | None
    up_30d: int | None
    down_30d: int | None

    @classmethod
    def fiscal_years(cls, rows: Sequence[RevisionRow]) -> list[RevisionRead]:
        by_period = {row.period: row for row in rows}
        return [
            cls.from_row(by_period[period], label)
            for period, label in FISCAL_YEARS
            if period in by_period
        ]

    @classmethod
    def from_row(cls, row: RevisionRow, label: str) -> RevisionRead:
        return cls(
            period=row.period,
            label=label,
            eps=_float(row.eps_current),
            change_30d=_change(row.eps_current, row.eps_30d),
            change_90d=_change(row.eps_current, row.eps_90d),
            up_30d=row.up_30d,
            down_30d=row.down_30d,
        )


def _change(current: Decimal | None, prior: Decimal | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return float((current - prior) / abs(prior))


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
