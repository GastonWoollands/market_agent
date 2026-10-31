from datetime import date, timedelta
from math import isclose
from types import SimpleNamespace

from api.ticker import Benchmarks, NameInputs, build_compare, build_ticker, parse_tickers

TODAY = date(2026, 10, 30)


def _series(n: int, *, step: float = 0.002, base: float = 100.0) -> list[tuple[date, float]]:
    out = []
    value = base
    for index in range(n):
        value *= 1 + (step if index % 3 else -step)
        out.append((TODAY - timedelta(days=n - index), value))
    return out


def _ttm(as_of: date, **kwargs) -> SimpleNamespace:
    row = {
        "revenue": 1000.0,
        "ebitda": 200.0,
        "ebit": 150.0,
        "cfo": 180.0,
        "capex": 60.0,
        "fcf": 120.0,
        "net_debt": 300.0,
        "interest_expense": 30.0,
        "shares": 10.0,
    }
    row.update(kwargs)
    return SimpleNamespace(as_of=as_of, **row)


def _name(ticker: str = "ACME", **kwargs) -> NameInputs:
    closes = kwargs.pop("closes", _series(300))
    return NameInputs(
        instrument=SimpleNamespace(
            ticker=ticker,
            name=f"{ticker} Corp",
            exchange="NYSE",
            sector=kwargs.pop("sector", "Industrials"),
            industry="Widgets",
            cik="0000000001",
        ),
        universes=kwargs.pop("universes", ["valuation"]),
        closes=closes,
        adj_closes=kwargs.pop("adj_closes", closes),
        ttm=kwargs.pop(
            "ttm",
            [
                _ttm(date(2025, 6, 30), revenue=800.0, ebitda=160.0, shares=9.0),
                _ttm(date(2026, 6, 30)),
            ],
        ),
        **kwargs,
    )


def _bench() -> Benchmarks:
    return Benchmarks(
        adj={"SPY": _series(300, step=0.001), "QQQ": _series(300), "XLI": _series(300)},
        sector_etf={"Industrials": "XLI"},
    )


def test_ticker_desk_reads_ratios_and_read_time_ev() -> None:
    page = build_ticker(_name(), _bench(), today=TODAY)
    desk = page.desk
    assert desk is not None
    close = page.price.close
    assert isclose(desk.market_cap, close * 10)
    assert desk.ev_basis == "read_time"
    assert isclose(desk.ev, close * 10 + 300)
    assert isclose(desk.ev_ebitda, desk.ev / 200)
    assert isclose(desk.interest_coverage, 5.0)
    assert isclose(desk.revenue_growth_1y, 0.25)
    assert isclose(desk.share_change_1y, 10 / 9 - 1)
    assert isclose(desk.financing_gap, (60 - 180) / (close * 10))
    assert isclose(desk.nd_ebitda, 1.5)
    assert page.identity.sector_etf == "XLI"
    assert page.technicals.rel_sector_1y is not None
    assert page.risk.source == "read_time"
    assert page.hint is None


def test_stored_valuation_wins_only_for_members() -> None:
    value = SimpleNamespace(
        as_of=TODAY,
        ev=5000.0,
        ev_ebitda=25.0,
        pctile_5y=40.0,
        comparable=True,
        sample_size=1200,
        ebitda_growth_1y=0.1,
    )
    member = build_ticker(_name(valuation=value), _bench(), today=TODAY).desk
    assert member.ev_basis == "valuation_daily"
    assert member.ev_ebitda == 25.0
    former = build_ticker(
        _name(valuation=value, universes=["watchlist"]), _bench(), today=TODAY
    ).desk
    assert former.ev_basis == "read_time"
    assert former.pctile_5y is None


def test_unknown_net_debt_leaves_ev_blank() -> None:
    ttm = [_ttm(date(2026, 6, 30), net_debt=None)]
    page = build_ticker(_name(ttm=ttm, universes=[]), _bench(), today=TODAY)
    assert page.hint and "not refreshed" in page.hint
    desk = page.desk
    assert desk.ev is None
    assert desk.ev_ebitda is None
    assert desk.fcf_yield is None
    assert desk.nd_ebitda is None
    assert desk.interest_coverage is not None


def test_name_without_bars_gets_a_hint() -> None:
    page = build_ticker(_name(closes=[], adj_closes=[]), _bench(), today=TODAY)
    assert page.price is None
    assert page.technicals is None
    assert page.stale
    assert page.hint and "Watchlist" in page.hint


def test_compare_corr_overlay_and_missing() -> None:
    same = _series(300)
    items = [_name("AAA", closes=same), _name("BBB", closes=same)]
    tape = build_compare(
        items, _bench(), requested=["AAA", "BBB", "NOPE"], missing=["NOPE"], today=TODAY
    )
    assert tape.missing == ["NOPE"]
    assert tape.corr.tickers == ["AAA", "BBB"]
    assert isclose(tape.corr.matrix[0][1], 1.0)
    assert [item.ticker for item in tape.overlay] == ["AAA", "BBB", "SPY"]
    assert tape.overlay[0].points[0].value == 100.0
    assert len(tape.rows) == 2


def test_parse_tickers_dedupes_and_caps() -> None:
    assert parse_tickers(" msft,META,msft,,nvda ") == ["MSFT", "META", "NVDA"]
    assert len(parse_tickers(",".join(f"T{i}" for i in range(10)))) == 6
