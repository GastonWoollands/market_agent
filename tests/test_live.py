from datetime import UTC, date, datetime
from decimal import Decimal

from api.live import build_live
from api.schemas import LiveRiskOn
from store.catalog import (
    CatalogInstrument,
    FredSeriesFile,
    FredSeriesItem,
    LiveHeaderItem,
    LiveTapeConfig,
    PolymarketEvent,
    PolymarketFile,
    UniverseCatalog,
    UniversesFile,
)
from store.display import resolve_change_pct, resolve_level_change, resolve_price
from store.models import OddsSnapshot
from store.repos import LiveMacroRow, LiveTapeRow


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
    assert tape.macro == []


def test_build_live_macro_uses_level_change_not_percent_return() -> None:
    fred = FredSeriesFile(
        series=[
            FredSeriesItem(
                id="DGS10",
                name="10Y Treasury yield",
                unit="percent",
                category="rates",
            )
        ]
    )
    rows = [
        LiveMacroRow(
            series_id="DGS10",
            last=Decimal("4.25"),
            prev=Decimal("4.20"),
            last_date=date(2026, 8, 14),
        )
    ]
    tape = build_live(
        [],
        _catalog(),
        now=datetime(2026, 8, 14, tzinfo=UTC),
        macro_rows=rows,
        fred=fred,
    )
    assert tape.macro[0].series_id == "DGS10"
    assert tape.macro[0].value == 4.25
    assert tape.macro[0].change == 0.05
    assert tape.macro[0].as_of == date(2026, 8, 14)
    assert resolve_level_change(Decimal("4.25"), Decimal("4.20")) == Decimal("0.05")


def test_build_live_drilldown_uses_yaml_insight_and_level_deltas() -> None:
    fred = FredSeriesFile(
        series=[
            FredSeriesItem(
                id="DGS10",
                name="10Y Treasury yield",
                unit="percent",
                insight="The discount rate on everything.",
                watch=["XLK"],
            )
        ]
    )
    history = [
        (date(2025, 8, 14), Decimal("4.00")),
        (date(2026, 8, 13), Decimal("4.20")),
        (date(2026, 8, 14), Decimal("4.25")),
    ]
    rows = [
        LiveTapeRow(
            ticker="XLK",
            name="Information Technology",
            quote_price=Decimal("228.1"),
            quote_change_pct=Decimal("1.2"),
            market_state="CLOSED",
            as_of=datetime(2026, 8, 14, tzinfo=UTC),
            last_close=Decimal("226"),
            prev_close=Decimal("225"),
            last_date=date(2026, 8, 14),
        )
    ]
    tape = build_live(
        rows,
        _catalog(),
        now=datetime(2026, 8, 14, tzinfo=UTC),
        fred=fred,
        lever="DGS10",
        history=history,
    )
    assert tape.drilldown is not None
    assert tape.drilldown.series_id == "DGS10"
    assert tape.drilldown.insight == "The discount rate on everything."
    assert tape.drilldown.value == 4.25
    assert tape.drilldown.deltas.d1 == 0.05
    assert tape.drilldown.deltas.y1 == 0.25
    assert tape.drilldown.watch[0].ticker == "XLK"
    assert tape.drilldown.watch[0].change_pct == 1.2
    assert tape.drilldown.points[-1].value == 4.25


def test_build_live_odds_do_not_affect_risk_on() -> None:
    risk = LiveRiskOn(score=0.42, stale=False, factors={"curve": 0.1})
    catalog = PolymarketFile(
        events=[
            PolymarketEvent(
                slug="us-recession-by-end-of-2026",
                label="Recession by year-end",
                category="growth",
            ),
            PolymarketEvent(
                slug="hidden",
                label="Hidden",
                category="rates",
                show_on_live=False,
            ),
        ]
    )
    row = OddsSnapshot(
        slug="us-recession-by-end-of-2026",
        as_of=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
        question="US recession by end of 2026?",
        implied_yes=Decimal("0.075"),
        liquidity=Decimal("40000"),
        raw={
            "closed": False,
            "markets": [{"question": "US recession by end of 2026?", "yes": "0.075"}],
        },
    )
    tape = build_live(
        [],
        _catalog(),
        now=datetime(2026, 8, 18, tzinfo=UTC),
        risk_on=risk,
        odds_rows=[row],
        polymarket=catalog,
    )
    assert tape.risk_on is not None
    assert tape.risk_on.score == 0.42
    assert tape.risk_on.factors == {"curve": 0.1}
    assert [item.slug for item in tape.odds] == ["us-recession-by-end-of-2026"]
    assert tape.odds[0].implied_yes == 0.075
    assert tape.odds[0].thin is False
