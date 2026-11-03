"""CFTC TFF positioning for Dynamics: asset managers and leveraged funds, against 3 years."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from analytics.positioning import WEEKS_3Y, PositioningRead, TraderNet
from api.schemas import PositioningResponse, PositioningRow, PositioningTrader
from store.catalog import CftcFile
from store.repos import cot_history

LOOKBACK_DAYS = WEEKS_3Y * 7 + 14


class PositioningView:
    """One row per catalog contract, in catalog order; contracts with no reports stay empty."""

    def __init__(self, catalog: CftcFile, history: dict[str, Sequence[Any]]) -> None:
        self._catalog = catalog
        self._history = history

    def response(self) -> PositioningResponse:
        rows = [
            self._row(contract.key, contract.label, contract.code)
            for contract in self._catalog.contracts
        ]
        dates = [row.report_date for row in rows if row.report_date is not None]
        return PositioningResponse(as_of=max(dates) if dates else None, rows=rows)

    def _row(self, key: str, label: str, code: str) -> PositioningRow:
        read = PositioningRead.from_history(self._history.get(code, []))
        if read is None:
            return PositioningRow(key=key, label=label)
        return PositioningRow(
            key=key,
            label=label,
            report_date=read.report_date,
            open_interest=read.open_interest,
            asset_managers=_trader(read.asset_managers),
            leveraged_funds=_trader(read.leveraged_funds),
        )


def load_positioning(db: Any, catalog: CftcFile, *, today: date) -> PositioningResponse:
    history = cot_history(db, catalog.codes(), start=today - timedelta(days=LOOKBACK_DAYS))
    return PositioningView(catalog, history).response()


def _trader(net: TraderNet) -> PositioningTrader:
    return PositioningTrader(
        net=net.net, share_oi=net.share_oi, change_1w=net.change_1w, pct_3y=net.pct_3y
    )
