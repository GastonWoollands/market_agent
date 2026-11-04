from datetime import UTC, date, datetime

from analytics.session import MarketClock, close_at


def _at(day: int, hour: int, minute: int = 0) -> MarketClock:
    return MarketClock(datetime(2026, 11, day, hour, minute, tzinfo=UTC))


def test_state_by_et_wall_clock() -> None:
    assert _at(3, 8, 59).state == "CLOSED"  # 03:59 ET
    assert _at(3, 9).state == "PRE"  # 04:00 ET
    assert _at(3, 14, 30).state == "REGULAR"  # 09:30 ET
    assert _at(3, 21).state == "POST"  # 16:00 ET
    assert _at(4, 1).state == "CLOSED"  # 20:00 ET Tuesday
    assert _at(7, 15).state == "CLOSED"  # Saturday


def test_naive_input_is_read_as_utc() -> None:
    assert MarketClock(datetime(2026, 11, 3, 15, 0)).is_regular


def test_close_at_is_1600_et() -> None:
    assert close_at(date(2026, 11, 3)) == datetime(2026, 11, 3, 21, 0, tzinfo=UTC)
