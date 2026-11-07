from dataclasses import dataclass
from datetime import date

from analytics.bank import BankRead


@dataclass
class _Row:
    as_of: date
    net_income: float | None
    equity: float | None
    shares: float | None = 4_800.0
    source: str = "yahoo"


def test_pe_pb_and_average_roe() -> None:
    rows = [
        _Row(date(2025, 6, 30), 2_000.0, 11_000.0),
        _Row(date(2026, 6, 30), 3_600.0, 13_000.0),
    ]
    read = BankRead.from_ttm(rows, close=12.0)
    assert read is not None
    assert read.market_cap == 57_600.0
    assert read.pe == 16.0
    assert round(read.pb, 3) == round(57_600 / 13_000, 3)
    assert read.roe == 3_600.0 / 12_000.0
    assert read.roe_basis == "average"
    assert read.source == "yahoo"


def test_without_a_year_old_row_roe_uses_ending_equity() -> None:
    rows = [
        _Row(date(2026, 3, 31), 3_200.0, 12_500.0),
        _Row(date(2026, 6, 30), 3_600.0, 13_000.0),
    ]
    read = BankRead.from_ttm(rows, close=12.0)
    assert read is not None
    assert read.roe == 3_600.0 / 13_000.0
    assert read.roe_basis == "ending"


def test_losses_and_missing_price_leave_ratios_empty() -> None:
    read = BankRead.from_ttm([_Row(date(2026, 6, 30), -100.0, 1_000.0)], close=None)
    assert read is not None
    assert read.pe is None and read.pb is None and read.market_cap is None
    assert BankRead.from_ttm([], close=10.0) is None
