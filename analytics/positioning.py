"""CFTC Traders in Financial Futures: who is net long or short, against three years.

Net = long − short contracts for a trader class, scaled by open interest so the read
survives open-interest growth. The percentile is the share of the last three years of
weekly reports at or below this week's net share.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

WEEKS_3Y = 156
MIN_WEEKS = 78


class CotRow(Protocol):
    report_date: date
    open_interest: int
    asset_mgr_long: int
    asset_mgr_short: int
    lev_money_long: int
    lev_money_short: int


@dataclass(frozen=True)
class TraderNet:
    net: int
    share_oi: float
    change_1w: int | None
    pct_3y: float | None


@dataclass(frozen=True)
class PositioningRead:
    report_date: date
    open_interest: int
    asset_managers: TraderNet
    leveraged_funds: TraderNet

    @classmethod
    def from_history(cls, rows: Sequence[CotRow]) -> PositioningRead | None:
        """`rows` oldest first for one contract; None when nothing is stored."""
        if not rows:
            return None
        window = list(rows)[-WEEKS_3Y:]
        latest = window[-1]
        return cls(
            report_date=latest.report_date,
            open_interest=latest.open_interest,
            asset_managers=_trader(window, "asset_mgr"),
            leveraged_funds=_trader(window, "lev_money"),
        )


def _trader(window: Sequence[CotRow], prefix: str) -> TraderNet:
    nets = [_net(row, prefix) for row in window]
    shares = [
        net / row.open_interest if row.open_interest else 0.0
        for net, row in zip(nets, window, strict=True)
    ]
    today = shares[-1]
    pct = (
        sum(1 for share in shares if share <= today) / len(shares)
        if len(shares) >= MIN_WEEKS
        else None
    )
    return TraderNet(
        net=nets[-1],
        share_oi=today,
        change_1w=nets[-1] - nets[-2] if len(nets) > 1 else None,
        pct_3y=pct,
    )


def _net(row: CotRow, prefix: str) -> int:
    return int(getattr(row, f"{prefix}_long")) - int(getattr(row, f"{prefix}_short"))
