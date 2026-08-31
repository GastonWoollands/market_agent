from datetime import UTC, date, datetime
from decimal import Decimal

from api.live import (
    anomaly_models,
    build_live,
    liquidity_model,
    live_brief,
    live_event_models,
    net_liquidity_from_store,
    regime_model,
)
from api.schemas import LiveBrief, LiveOutlier, LiveRiskOn
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
    eem = CatalogInstrument(
        ticker="EEM",
        yahoo="EEM",
        name="Emerging Markets",
        role="intl",
    )
    return UniversesFile(
        tape=UniverseCatalog(instruments=[gspc, xlk, eem]),
        watchlist=UniverseCatalog(),
        live=LiveTapeConfig(
            header=[LiveHeaderItem(ticker="^GSPC", label="S&P 500")],
            mover_roles=["sector", "group"],
            intl_section=[LiveHeaderItem(ticker="EEM", label="Emerging Markets")],
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


def test_build_live_skips_pack_only_fred_series() -> None:
    fred = FredSeriesFile(
        series=[
            FredSeriesItem(id="DGS10", name="10Y", unit="percent"),
            FredSeriesItem(
                id="DEXUSEU",
                name="USD per EUR",
                unit="usd_per_eur",
                show_on_live=False,
            ),
        ]
    )
    tape = build_live(
        [],
        _catalog(),
        now=datetime(2026, 8, 14, tzinfo=UTC),
        fred=fred,
    )
    assert [item.series_id for item in tape.macro] == ["DGS10"]


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


def test_build_live_sorts_movers_and_labels_change_kind() -> None:
    xlp = CatalogInstrument(ticker="XLP", yahoo="XLP", name="Staples", role="sector")
    catalog = _catalog()
    catalog.tape.instruments.append(xlp)
    as_of = datetime(2026, 8, 14, 16, 0, tzinfo=UTC)
    rows = [
        LiveTapeRow(
            ticker="XLK",
            name="Information Technology",
            quote_price=Decimal("228"),
            quote_change_pct=Decimal("-0.5"),
            market_state="REGULAR",
            as_of=as_of,
            last_close=Decimal("228"),
            prev_close=Decimal("229"),
            last_date=date(2026, 8, 14),
        ),
        LiveTapeRow(
            ticker="XLP",
            name="Staples",
            quote_price=Decimal("80"),
            quote_change_pct=Decimal("1.4"),
            market_state="REGULAR",
            as_of=as_of,
            last_close=Decimal("80"),
            prev_close=Decimal("79"),
            last_date=date(2026, 8, 14),
        ),
    ]
    tape = build_live(rows, catalog, now=as_of)
    assert [item.ticker for item in tape.movers] == ["XLP", "XLK"]
    assert tape.movers[0].change_kind == "session"
    assert tape.header[0].change_kind is None


def test_build_live_attaches_events_brief_and_watchlist_outliers() -> None:
    as_of = datetime(2026, 8, 14, 16, 0, tzinfo=UTC)
    watch = [
        LiveTapeRow(
            ticker="NVDA",
            name="NVIDIA",
            quote_price=Decimal("180"),
            quote_change_pct=Decimal("3.2"),
            market_state="REGULAR",
            as_of=as_of,
            last_close=Decimal("180"),
            prev_close=Decimal("174"),
            last_date=date(2026, 8, 14),
        ),
        LiveTapeRow(
            ticker="AAPL",
            name="Apple",
            quote_price=Decimal("220"),
            quote_change_pct=Decimal("-0.2"),
            market_state="REGULAR",
            as_of=as_of,
            last_close=Decimal("220"),
            prev_close=Decimal("220.4"),
            last_date=date(2026, 8, 14),
        ),
    ]
    tape = build_live(
        [],
        _catalog(),
        now=as_of,
        events=live_event_models(
            [{"date": "2026-08-14", "title": "CPI (July)", "kind": "cpi", "source": "yaml"}]
        ),
        brief=LiveBrief(headline="Tape", live_md="CPI is the print.", expect="CPI 08:30."),
        outliers=[LiveOutlier(id="DEXJPUS", window="1d", change=-1.2, z=2.1)],
        watchlist_rows=watch,
    )
    assert tape.events[0].kind == "cpi"
    assert tape.brief is not None
    assert tape.brief.live_md == "CPI is the print."
    assert tape.outliers[0].id == "DEXJPUS"
    assert [item.ticker for item in tape.watchlist_outliers] == ["NVDA", "AAPL"]


def test_live_event_models_keep_yesterday_speech() -> None:
    events = live_event_models(
        [
            {
                "date": "2026-08-28",
                "title": "Jackson Hole Chair keynote",
                "kind": "speech",
                "source": "yaml",
            }
        ]
    )
    assert events[0].kind == "speech"
    assert events[0].date == date(2026, 8, 28)
    assert events[0].title == "Jackson Hole Chair keynote"


def test_build_live_maps_intl_section() -> None:
    as_of = datetime(2026, 8, 14, 16, 0, tzinfo=UTC)
    rows = [
        LiveTapeRow(
            ticker="EEM",
            name="Emerging Markets",
            quote_price=Decimal("45.5"),
            quote_change_pct=Decimal("0.8"),
            market_state="REGULAR",
            as_of=as_of,
            last_close=Decimal("45.5"),
            prev_close=Decimal("45.1"),
            last_date=date(2026, 8, 14),
        )
    ]
    tape = build_live(rows, _catalog(), now=as_of)
    assert [item.ticker for item in tape.intl] == ["EEM"]
    assert tape.intl[0].name == "Emerging Markets"
    assert tape.intl[0].change_pct == 0.8
    # intl names are not part of the sector movers list
    assert all(item.ticker != "EEM" for item in tape.movers)


def test_build_live_passes_regime_liquidity_anomalies() -> None:
    from analytics.anomaly_detect import Anomaly

    class _Regime:
        as_of = date(2026, 8, 14)
        growth_regime = "expansion"
        inflation_regime = "decelerating"
        policy_regime = "neutral"
        volatility_regime = "suppressed"
        growth_confidence = Decimal("0.85")
        inflation_confidence = Decimal("0.80")
        policy_confidence = Decimal("0.70")
        volatility_confidence = Decimal("0.85")

    regime = regime_model(_Regime())
    liquidity = liquidity_model(
        {
            "net_liquidity_bn": 5800.0,
            "wow_change_bn": -25.0,
            "components": {"fed_bs_bn": 7000.0, "rrp_bn": 500.0, "tga_bn": 700.0},
        }
    )
    anomalies = anomaly_models(
        [
            Anomaly(
                type="z_score_extreme",
                description="SMH moved 2.4 std devs",
                severity=0.8,
                components={},
            )
        ]
    )
    tape = build_live(
        [],
        _catalog(),
        now=datetime(2026, 8, 14, tzinfo=UTC),
        regime=regime,
        liquidity=liquidity,
        anomalies=anomalies,
    )
    assert tape.regime is not None
    assert tape.regime.growth == "expansion"
    assert tape.regime.growth_confidence == 0.85
    assert tape.liquidity is not None
    assert tape.liquidity.net_liquidity_bn == 5800.0
    assert tape.liquidity.wow_change_bn == -25.0
    assert tape.liquidity.rrp_bn == 500.0
    assert tape.anomalies[0].type == "z_score_extreme"
    assert tape.anomalies[0].severity == 0.8


def test_regime_model_none_and_unknown() -> None:
    assert regime_model(None) is None


def test_net_liquidity_from_store_computes_billions() -> None:
    def _daily(base: float) -> list[tuple[date, Decimal]]:
        return [
            (date(2026, 8, 1), Decimal(str(base - 100))),
            (date(2026, 8, 7), Decimal(str(base - 50))),
            (date(2026, 8, 14), Decimal(str(base))),
        ]

    points = {
        "WALCL": _daily(7_000_000),  # $7.0T in millions
        "RRPONTSYD": _daily(500_000),  # $0.5T
        "WTREGEN": _daily(700_000),  # $0.7T
    }
    result = net_liquidity_from_store(points)
    assert result is not None
    # (7.0 - 0.5 - 0.7)T = 5.8T = 5800B
    assert result["net_liquidity_bn"] == 5800.0
    model = liquidity_model(result)
    assert model is not None
    assert model.fed_bs_bn == 7000.0


def test_net_liquidity_from_store_missing_series_returns_none() -> None:
    assert net_liquidity_from_store({"WALCL": [(date(2026, 8, 14), Decimal("7000000"))]}) is None


def test_live_brief_empty_without_fields() -> None:
    class _Report:
        as_of = date(2026, 8, 18)
        status = "ok"
        body_json = {"macro_md": "DGS10 4.68"}

    assert live_brief(_Report()) is None
    class _Full:
        as_of = date(2026, 8, 18)
        status = "ok"
        body_json = {"headline": "Tape", "live_md": "Hello.", "expect": "CPI"}

    attached = live_brief(_Full())
    assert attached is not None
    assert attached.headline == "Tape"
