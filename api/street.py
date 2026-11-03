"""Short interest and street EPS revisions for the Ticker page. Reads only."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from analytics.street import RevisionRead, ShortInterestRead
from api.schemas import TickerRevision, TickerShortInterest, TickerStreet
from store.repos import latest_eps_revisions, latest_shares, latest_short_interest

NO_REVISIONS = (
    "No street estimates stored (revisions cover the watchlist and the Opportunities top 25)."
)


class StreetView:
    def __init__(self, short: Any | None, shares: Decimal | None, revisions: Sequence[Any]) -> None:
        self._short = short
        self._shares = shares
        self._revisions = revisions

    def response(self) -> TickerStreet:
        reads = RevisionRead.fiscal_years(self._revisions)
        return TickerStreet(
            short=self._short_model(),
            revisions_as_of=self._revisions[0].as_of if reads else None,
            revisions=[TickerRevision(**asdict(read)) for read in reads],
            revisions_unavailable=None if reads else NO_REVISIONS,
        )

    def _short_model(self) -> TickerShortInterest | None:
        if self._short is None:
            return None
        read = ShortInterestRead.from_row(self._short, self._shares)
        return TickerShortInterest(**asdict(read))


def load_ticker_street(db: Any, instrument_id: int) -> TickerStreet:
    return StreetView(
        latest_short_interest(db, instrument_id),
        latest_shares(db, instrument_id),
        latest_eps_revisions(db, instrument_id),
    ).response()
