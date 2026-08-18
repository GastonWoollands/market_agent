from datetime import UTC, date, datetime
from decimal import Decimal

from api.live import build_live
from store.catalog import (
    CatalogInstrument,
    LiveHeaderItem,
    LiveTapeConfig,
    UniverseCatalog,
    UniversesFile,
)
from store.display import resolve_change_pct, resolve_price
from store.repos import LiveTapeRow


def _catalog() -> UniversesFile:
    xlk = CatalogInstrument(
        ticker="XLK",
        yahoo="XLK",
        name="Information Technology",
        role="sector",
    )
    gspc = CatalogInstrument(
        ticker="^GSPC",
        yahoo="^GSPC",
        name="S&P 500",
        role="index",
    )
    return UniversesFile(
        tape=UniverseCatalog(instruments=[gspc, xlk]),
        watchlist=UniverseCatalog(),
        live=LiveTapeConfig(
            header=[LiveHeaderItem(ticker="^GSPC", label="S&P 500")],
            mover_roles=["sector", "group"],
        ),
    )


def test_resolve_change_pct_prefers_quote() -> None:
    assert resolve_price(Decimal("10"), Decimal("9")) == Decimal("10")
    assert resolve_change_pct(Decimal("1.5"), Decimal("110"), Decimal("100")) == Decimal("1.5")


def test_resolve_change_pct_falls_back_to_closes() -> None:
    assert resolve_price(None, Decimal("110")) == Decimal("110")
    assert resolve_change_pct(None, Decimal("110"), Decimal("100")) == Decimal("10")
    assert resolve_change_pct(None, Decimal("110"), Decimal("0")) is None
    assert resolve_change_pct(None, None, Decimal("100")) is None


def test_build_live_uses_bar_fallback_and_yaml_order() -> None:
    rows = [
        LiveTapeRow(
            ticker="XLK",
            name="Information Technology",
            quote_price=None,
            quote_change_pct=None,
            market_state=None,
            as_of=None,
            last_close=Decimal("110"),
            prev_close=Decimal("100"),
            last_date=date(2026, 8, 14),
        )
    ]
    tape = build_live(rows, _catalog(), now=datetime(2026, 8, 14, tzinfo=UTC))
    assert tape.header[0].ticker == "^GSPC"
    assert tape.header[0].price is None
    assert tape.movers[0].ticker == "XLK"
    assert tape.movers[0].price == 110.0
    assert tape.movers[0].change_pct == 10.0
    assert tape.stale is True
    assert tape.market_state is None


def test_build_live_quote_wins_and_session_state() -> None:
    as_of = datetime(2026, 8, 14, 16, 0, tzinfo=UTC)
    rows = [
        LiveTapeRow(
            ticker="^GSPC",
            name="S&P 500",
            quote_price=Decimal("5500.25"),
            quote_change_pct=Decimal("0.42"),
            market_state="CLOSED",
            as_of=as_of,
            last_close=Decimal("5490"),
            prev_close=Decimal("5480"),
            last_date=date(2026, 8, 14),
        ),
        LiveTapeRow(
            ticker="XLK",
            name="Information Technology",
            quote_price=Decimal("228.1"),
            quote_change_pct=Decimal("1.2"),
            market_state="REGULAR",
            as_of=as_of,
            last_close=Decimal("226"),
            prev_close=Decimal("225"),
            last_date=date(2026, 8, 14),
        ),
    ]
    tape = build_live(rows, _catalog(), now=as_of)
    assert tape.header[0].price == 5500.25
    assert tape.header[0].change_pct == 0.42
    assert tape.market_state == "CLOSED"
    assert tape.stale is False
    assert tape.as_of == as_of
