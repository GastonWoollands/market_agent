from datetime import UTC, date, datetime
from decimal import Decimal

from api.watchlist import build_watchlist
from store.repos import LiveTapeRow


def test_watchlist_uses_db_quote_and_tv_symbol() -> None:
    as_of = datetime(2026, 8, 18, 16, 0, tzinfo=UTC)
    rows = [
        LiveTapeRow(
            ticker="NVDA",
            name="NVIDIA",
            quote_price=Decimal("180.25"),
            quote_change_pct=Decimal("1.5"),
            market_state="CLOSED",
            as_of=as_of,
            last_close=Decimal("178.00"),
            prev_close=Decimal("177.00"),
            last_date=date(2026, 8, 18),
        )
    ]
    tape = build_watchlist(
        rows,
        sparklines={
            "NVDA": [
                (date(2026, 6, 1), Decimal("100")),
                (date(2026, 8, 18), Decimal("180.25")),
            ]
        },
        intraday={"NVDA": [(as_of.replace(hour=13, minute=30), Decimal("179.5"))]},
        selected="NVDA",
        now=as_of,
    )
    assert tape.selected == "NVDA"
    assert tape.stale is False
    member = tape.members[0]
    assert member.price == 180.25
    assert member.change_pct == 1.5
    assert member.tv_symbol == "NVDA"
    assert member.sparkline[-1].value == 180.25
    assert len(member.intraday) == 1
    assert member.as_of == as_of


def test_watchlist_falls_back_to_daily_close_without_quote() -> None:
    rows = [
        LiveTapeRow(
            ticker="^GSPC",
            name="S&P 500",
            quote_price=None,
            quote_change_pct=None,
            market_state=None,
            as_of=None,
            last_close=Decimal("5500"),
            prev_close=Decimal("5400"),
            last_date=date(2026, 8, 18),
        )
    ]
    tape = build_watchlist(
        rows,
        sparklines={"^GSPC": [(date(2026, 8, 18), Decimal("5500"))]},
        intraday={},
        selected=None,
        now=datetime(2026, 8, 18, tzinfo=UTC),
    )
    assert tape.members[0].price == 5500.0
    assert tape.members[0].change_pct == 1.8519
    assert tape.members[0].tv_symbol == "SPX"
    assert tape.selected == "^GSPC"
    assert tape.stale is True
