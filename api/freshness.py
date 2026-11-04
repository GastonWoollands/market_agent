"""Freshness strip: how current each data domain is versus the last US session.

Reads `FreshnessDates` from Postgres; nothing is fetched. No holiday calendar, so a
market holiday reads one session late until the next run.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from api.schemas import FreshnessItem, FreshnessResponse
from store.repos import FreshnessDates

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
TTM_MAX_AGE = timedelta(days=150)
TTM_LATE_SHARE = 0.10
MACRO_LAG_SESSIONS = 2


def last_session(now: datetime) -> date:
    """Most recent weekday whose cash session has opened, in ET."""
    return _last_weekday_past(now, SESSION_OPEN)


def last_close(now: datetime) -> date:
    """Most recent weekday whose cash session has closed, in ET."""
    return _last_weekday_past(now, SESSION_CLOSE)


def _last_weekday_past(now: datetime, cutoff: time) -> date:
    local = now.astimezone(ET)
    day = local.date()
    if local.weekday() < 5 and local.time() >= cutoff:
        return day
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def sessions_between(start: date, end: date) -> int:
    """Weekdays after `start` up to and including `end`."""
    count = 0
    day = start
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count


class FreshnessView:
    """Stored dates -> one status per domain for the app chrome."""

    def __init__(self, dates: FreshnessDates, *, now: datetime | None = None) -> None:
        self._dates = dates
        self._now = now or datetime.now(UTC)
        self._session = last_session(self._now)
        self._close = last_close(self._now)

    @staticmethod
    def ttm_cutoff(now: datetime | None = None) -> date:
        return (now or datetime.now(UTC)).astimezone(ET).date() - TTM_MAX_AGE

    def response(self) -> FreshnessResponse:
        return FreshnessResponse(
            session=self._session,
            items=[
                self._prices(),
                self._macro(),
                self._filings(),
                self._scores(),
                self._rotation(),
                self._outlook(),
            ],
        )

    def _prices(self) -> FreshnessItem:
        stamp = self._dates.quotes_as_of
        if stamp is None:
            return _missing("prices", "Prices")
        late = stamp.astimezone(ET).date() < self._session
        return _item("prices", "Prices", stamp.isoformat(), late, "Delayed Yahoo quotes")

    def _macro(self) -> FreshnessItem:
        last = self._dates.dgs10_last
        if last is None:
            return _missing("macro", "Macro")
        lag = sessions_between(last, self._session)
        note = f"FRED daily series, {lag} session(s) behind (10Y)"
        return _item("macro", "Macro", last.isoformat(), lag > MACRO_LAG_SESSIONS, note)

    def _filings(self) -> FreshnessItem:
        finished = self._dates.sec_finished_at
        if finished is None:
            return _missing("filings", "Filings")
        names = self._dates.ttm_names
        old = self._dates.ttm_older_than_cutoff
        late = names > 0 and old / names > TTM_LATE_SHARE
        note = f"{old} of {names} names have a latest TTM older than {TTM_MAX_AGE.days} days"
        stamp = finished.astimezone(ET).date().isoformat()
        return _item("filings", "Filings", stamp, late, note)

    def _scores(self) -> FreshnessItem:
        return self._vs_last_bar("scores", "Valuation", self._dates.scores_as_of)

    def _rotation(self) -> FreshnessItem:
        return self._vs_last_bar("rotation", "Rotation", self._dates.rrg_as_of)

    def _outlook(self) -> FreshnessItem:
        as_of = self._dates.outlook_as_of
        if as_of is None:
            return _missing("outlook", "Outlook")
        return _item("outlook", "Outlook", as_of.isoformat(), as_of < self._session, None)

    def _vs_last_bar(self, key: str, label: str, as_of: date | None) -> FreshnessItem:
        if as_of is None:
            return _missing(key, label)
        bar = self._dates.spy_last_bar
        if bar is None:
            return _item(key, label, as_of.isoformat(), True, "No SPY daily bars stored")
        if bar < self._close:
            # Bars stopped: the computed output cannot be current either.
            note = f"Daily bars stop at {bar.isoformat()}; last close {self._close.isoformat()}"
            return _item(key, label, as_of.isoformat(), True, note)
        # Today's partial bar is not a close yet; compare with the last completed session.
        late = as_of < self._close
        return _item(key, label, as_of.isoformat(), late, f"Last daily close {self._close}")


def _item(key: str, label: str, as_of: str, late: bool, note: str | None) -> FreshnessItem:
    return FreshnessItem(
        key=key, label=label, as_of=as_of, status="late" if late else "ok", note=note
    )


def _missing(key: str, label: str) -> FreshnessItem:
    return FreshnessItem(key=key, label=label, as_of=None, status="missing", note="No stored data")
