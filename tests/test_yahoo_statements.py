"""Yahoo quarterly statements -> TTM for curated foreign filers (Phase 1.15). No network."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from ingest.yahoo.errors import YahooParseError
from ingest.yahoo.parse import quarterly_statements_from_frames
from ingest.yahoo.statements import StatementTtm

ENDS = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]


def _frame(rows: dict[str, list[float | None]], ends: list[str] = ENDS) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.to_datetime(ends)).T


def _frames(*, bank: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    income = {
        "Total Revenue": [400.0, 300.0, 300.0, 300.0, 200.0],
        "Net Income Common Stockholders": [50.0, 40.0, 40.0, 40.0, 30.0],
        "Reconciled Depreciation": [10.0, 10.0, 10.0, 10.0, 10.0],
    }
    if not bank:
        income["Operating Income"] = [60.0, 50.0, 50.0, 50.0, 40.0]
    balance = {
        "Total Debt": [130.0, 130.0, 130.0, 130.0, 130.0],
        "Capital Lease Obligations": [30.0, 30.0, 30.0, 30.0, 30.0],
        "Cash And Cash Equivalents": [500.0, 400.0, 400.0, 400.0, 400.0],
        "Stockholders Equity": [900.0, 850.0, 800.0, 800.0, 800.0],
        "Ordinary Shares Number": [250.0, 250.0, 250.0, 250.0, 250.0],
    }
    cashflow = {
        "Operating Cash Flow": [80.0, 70.0, 70.0, 70.0, 60.0],
        "Capital Expenditure": [-5.0, -5.0, -5.0, -5.0, -5.0],
    }
    return _frame(income), _frame(balance), _frame(cashflow)


def test_frames_become_quarters_newest_last_with_debt_ex_leases() -> None:
    quarters = quarterly_statements_from_frames("DLO", "USD", *_frames())
    assert [item.period_end for item in quarters] == sorted(
        date.fromisoformat(end) for end in ENDS
    )
    last = quarters[-1]
    assert last.revenue == Decimal("400.0")
    assert last.capex == Decimal("5.0")
    assert last.debt == Decimal("100.0")


def test_five_quarters_make_two_ttm_points() -> None:
    quarters = quarterly_statements_from_frames("DLO", "USD", *_frames())
    result = StatementTtm.from_quarters(quarters, cik="0001846832")
    assert result.skipped is None
    assert [item.as_of for item in result.points] == [date(2026, 3, 31), date(2026, 6, 30)]
    latest = result.points[-1]
    assert latest.revenue == Decimal("1300.0")
    assert latest.ebit == Decimal("210.0")
    assert latest.ebitda == Decimal("250.0")
    assert latest.fcf == Decimal("270.0")
    assert latest.net_debt == Decimal("-400.0")
    assert latest.net_income == Decimal("170.0")
    assert latest.equity == Decimal("900.0")


def test_adr_ratio_divides_ordinary_shares() -> None:
    quarters = quarterly_statements_from_frames("PAM", "USD", *_frames())
    result = StatementTtm.from_quarters(quarters, cik="1", adr_ratio=Decimal(25))
    assert result.points[-1].shares == Decimal(10)


def test_bank_without_operating_income_has_no_ebitda() -> None:
    quarters = quarterly_statements_from_frames("NU", "USD", *_frames(bank=True))
    latest = StatementTtm.from_quarters(quarters, cik="0001691493").points[-1]
    assert latest.ebitda is None
    assert latest.ebit is None
    assert latest.net_income == Decimal("170.0")


def test_non_usd_statements_are_skipped() -> None:
    quarters = quarterly_statements_from_frames("YPF", "ARS", *_frames())
    result = StatementTtm.from_quarters(quarters, cik="0000904851")
    assert result.points == ()
    assert result.skipped == "non_usd"


def test_three_quarters_are_too_few() -> None:
    income, balance, cashflow = (frame.iloc[:, :3] for frame in _frames())
    quarters = quarterly_statements_from_frames("DLO", "USD", income, balance, cashflow)
    assert StatementTtm.from_quarters(quarters, cik="1").skipped == "few_quarters"


def test_gap_between_quarters_breaks_the_window() -> None:
    ends = ["2026-06-30", "2026-03-31", "2025-09-30", "2025-06-30", "2025-03-31"]
    income = _frame({"Total Revenue": [1.0, 1.0, 1.0, 1.0, 1.0]}, ends)
    quarters = quarterly_statements_from_frames("DLO", "USD", income, None, None)
    assert StatementTtm.from_quarters(quarters, cik="1").skipped == "few_quarters"


def test_missing_currency_fails_loud() -> None:
    with pytest.raises(YahooParseError):
        quarterly_statements_from_frames("DLO", None, *_frames())
