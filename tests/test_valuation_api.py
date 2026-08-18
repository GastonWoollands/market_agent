from datetime import date
from types import SimpleNamespace

from api.valuation import build_valuation


def _row(ticker: str, **kwargs) -> tuple:
    instrument = SimpleNamespace(
        ticker=ticker,
        name=kwargs.get("name", ticker),
        exchange=kwargs.get("exchange", "Nasdaq"),
        industry=kwargs.get("industry"),
        cik="0000320193",
    )
    metric = SimpleNamespace(
        revenue=kwargs.get("revenue", 2_000_000_000),
        fcf=1.0,
        net_debt=1.0,
    )
    value = SimpleNamespace(
        as_of=date(2026, 8, 14),
        ev=kwargs.get("ev", 10_000_000_000),
        ebitda=kwargs.get("ebitda", 1_000_000_000),
        ev_ebitda=kwargs.get("ev_ebitda", 10.0),
        pctile_5y=kwargs.get("pctile_5y", 40.0),
        ebitda_growth_1y=kwargs.get("growth", 0.1),
        multiple_change_1y=kwargs.get("rerate", -0.05),
        comparable=kwargs.get("comparable", True),
    )
    return instrument, metric, value


def test_comparable_n_of_m_is_not_the_filtered_count() -> None:
    rows = [
        _row("AAPL", industry="Tech", revenue=400_000_000_000, pctile_5y=80.0),
        _row("MSFT", industry="Tech", revenue=300_000_000_000, pctile_5y=20.0),
        _row("XOM", industry="Energy", revenue=50_000_000_000, pctile_5y=10.0, comparable=False),
    ]
    tape = build_valuation(
        rows,
        comparable_n=2,
        comparable_m=3,
        min_revenue=1_000_000_000,
        as_of=date(2026, 8, 14),
        stale=False,
        q="aapl",
        sort="pctile",
    )
    assert tape.comparable_n == 2
    assert tape.comparable_m == 3
    assert tape.count == 1
    assert tape.members[0].ticker == "AAPL"
    energy = build_valuation(
        rows,
        comparable_n=2,
        comparable_m=3,
        min_revenue=1_000_000_000,
        as_of=date(2026, 8, 14),
        stale=False,
        industry="Energy",
        sort="pctile",
    )
    assert energy.count == 1
    assert energy.members[0].ticker == "XOM"
    cheap = build_valuation(
        rows,
        comparable_n=2,
        comparable_m=3,
        min_revenue=1_000_000_000,
        as_of=date(2026, 8, 14),
        stale=False,
        sort="pctile",
    )
    assert [item.ticker for item in cheap.members] == ["XOM", "MSFT", "AAPL"]
