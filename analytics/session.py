"""US cash-session hours in ET: one definition for Live, the freshness strip and the pack.

No holiday calendar or early closes: a market holiday reads as a normal weekday session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PRE_OPEN = time(4, 0)
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
POST_CLOSE = time(20, 0)


class MarketClock:
    """One instant read against the US equity session (Yahoo-style state names)."""

    def __init__(self, now: datetime) -> None:
        aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        self.local = aware.astimezone(ET)

    @property
    def is_weekday(self) -> bool:
        return self.local.weekday() < 5

    @property
    def state(self) -> str:
        """PRE, REGULAR, POST or CLOSED by wall clock."""
        clock = self.local.time()
        if not self.is_weekday or clock < PRE_OPEN or clock >= POST_CLOSE:
            return "CLOSED"
        if clock < SESSION_OPEN:
            return "PRE"
        if clock < SESSION_CLOSE:
            return "REGULAR"
        return "POST"

    @property
    def is_regular(self) -> bool:
        return self.state == "REGULAR"

    def last_session(self) -> date:
        """Most recent weekday whose cash session has opened."""
        return self._last_weekday_past(SESSION_OPEN)

    def last_close(self) -> date:
        """Most recent weekday whose cash session has closed."""
        return self._last_weekday_past(SESSION_CLOSE)

    def _last_weekday_past(self, cutoff: time) -> date:
        day = self.local.date()
        if self.is_weekday and self.local.time() >= cutoff:
            return day
        day -= timedelta(days=1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return day


def close_at(day: date) -> datetime:
    """The cash close of `day` as an aware ET datetime."""
    return datetime.combine(day, SESSION_CLOSE, ET)


def sessions_between(start: date, end: date) -> int:
    """Weekdays after `start` up to and including `end`."""
    count = 0
    day = start
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count
