import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analytics.street import RevisionRead, ShortInterestRead
from api.street import NO_REVISIONS, StreetView
from ingest.finra.errors import FinraParseError
from ingest.finra.parse import finra_symbol, reports_from_rows, settlement_dates
from ingest.yahoo.parse import eps_revisions_from_frames

FIXTURE = Path(__file__).parent / "fixtures" / "finra_short_interest.json"
AS_OF = date(2026, 11, 3)


def test_finra_symbol_drops_class_separator() -> None:
    assert finra_symbol("BRK-B") == "BRKB"
    assert finra_symbol("msft") == "MSFT"


def test_finra_fixture_parses() -> None:
    reports = {row.symbol: row for row in reports_from_rows(json.loads(FIXTURE.read_text()))}
    assert set(reports) == {"BRKB", "CRWV", "MSFT"}
    msft = reports["MSFT"]
    assert msft.settlement_date == date(2026, 10, 15)
    assert msft.short_shares == 65674557
    assert msft.days_to_cover == Decimal("3.18")
    assert settlement_dates(
        [{"settlementDate": "2026-10-15"}, {"settlementDate": "2026-09-30"}]
    ) == [
        date(2026, 9, 30),
        date(2026, 10, 15),
    ]
    with pytest.raises(FinraParseError):
        reports_from_rows([{"symbolCode": "X", "settlementDate": "2026-10-15"}])


def test_eps_revisions_from_yfinance_frames() -> None:
    periods = pd.Index(["0q", "0y", "+1y"], name="period")
    trend = pd.DataFrame(
        {
            "current": [4.8, 20.0, 24.0],
            "7daysAgo": [4.8, 19.8, 23.7],
            "30daysAgo": [4.8, 19.75, 23.6],
            "60daysAgo": [4.8, 19.75, 23.6],
            "90daysAgo": [4.8, 19.7, 23.5],
            "currency": ["USD"] * 3,
        },
        index=periods,
    )
    revisions = pd.DataFrame(
        {
            "upLast7days": [5, 6, 7],
            "upLast30days": [8, 10, 13],
            "downLast30days": [7, 7, 3],
            "downLast7Days": [3, 1, 1],
        },
        index=periods,
    )
    rows = {row.period: row for row in eps_revisions_from_frames("MSFT", trend, revisions)}
    assert rows["0y"].eps_current == Decimal("20.0")
    assert rows["0y"].up_30d == 10 and rows["0y"].down_7d == 1
    assert eps_revisions_from_frames("SPY", pd.DataFrame(), pd.DataFrame()) == []


def _revision(period: str, current: str, d30: str, d90: str) -> SimpleNamespace:
    return SimpleNamespace(
        as_of=AS_OF,
        period=period,
        eps_current=Decimal(current),
        eps_30d=Decimal(d30),
        eps_90d=Decimal(d90),
        up_30d=3,
        down_30d=1,
    )


def test_revision_change_scales_by_abs_prior() -> None:
    rows = [
        _revision("+1y", "-4.5", "-5.0", "-4.0"),
        _revision("0y", "20", "19", "0"),
        _revision("0q", "1", "1", "1"),
    ]
    reads = RevisionRead.fiscal_years(rows)
    assert [read.period for read in reads] == ["0y", "+1y"]
    assert reads[0].change_30d == pytest.approx(1 / 19)
    assert reads[0].change_90d is None  # prior of zero
    assert reads[1].change_30d == pytest.approx(0.1)  # loss narrowing reads as up
    assert reads[1].change_90d == pytest.approx(-0.125)


def test_short_interest_share_of_outstanding() -> None:
    row = SimpleNamespace(
        settlement_date=date(2026, 10, 15),
        short_shares=50,
        days_to_cover=Decimal("2.5"),
        change_pct=Decimal("7.43"),
    )
    read = ShortInterestRead.from_row(row, Decimal(1000))
    assert read.share_of_outstanding == pytest.approx(0.05)
    assert read.change == pytest.approx(0.0743)
    assert ShortInterestRead.from_row(row, None).share_of_outstanding is None


def test_street_view_without_estimates() -> None:
    street = StreetView(None, None, []).response()
    assert street.short is None
    assert street.revisions == [] and street.revisions_unavailable == NO_REVISIONS
