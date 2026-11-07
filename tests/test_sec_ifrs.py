"""IFRS 20-F / 6-K filers (Phase 1.15): concept names differ from US GAAP."""

from datetime import date
from decimal import Decimal

from ingest.sec.parse import ttm_from_facts, ttm_history_from_facts, usable_ttm

M = 1_000_000


def _flow(start: str, end: str, val: int, form: str) -> dict[str, object]:
    return {"start": start, "end": end, "val": val, "form": form, "filed": end}


def _instant(end: str, val: int, form: str = "20-F") -> dict[str, object]:
    return {"end": end, "val": val, "form": form, "filed": end}


def _usd(*rows: dict[str, object]) -> dict[str, object]:
    return {"units": {"USD": list(rows)}}


def _annual_payload() -> dict:
    """A 20-F-only filer (like VIST): one fiscal year, IFRS tags, no quarters."""
    fy = ("2025-01-01", "2025-12-31")
    return {
        "cik": 1762506,
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [_instant("2025-12-31", 100 * M)]}
                }
            },
            "ifrs-full": {
                "Revenue": _usd(_flow(*fy, 1_600 * M, "20-F")),
                "ProfitLossFromOperatingActivities": _usd(_flow(*fy, 600 * M, "20-F")),
                "DepreciationAndAmortisationExpense": _usd(_flow(*fy, 400 * M, "20-F")),
                "CashFlowsFromUsedInOperatingActivities": _usd(_flow(*fy, 900 * M, "20-F")),
                "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": _usd(
                    _flow(*fy, 1_000 * M, "20-F")
                ),
                "ProfitLoss": _usd(_flow(*fy, 500 * M, "20-F")),
                "ProfitLossAttributableToOwnersOfParent": _usd(_flow(*fy, 450 * M, "20-F")),
                "Borrowings": _usd(_instant("2025-12-31", 1_000 * M)),
                "LeaseLiabilities": _usd(_instant("2025-12-31", 300 * M)),
                "CashAndCashEquivalents": _usd(_instant("2025-12-31", 250 * M)),
                "Liabilities": _usd(_instant("2025-12-31", 2_600 * M)),
                "Equity": _usd(_instant("2025-12-31", 1_700 * M)),
                "EquityAttributableToOwnersOfParent": _usd(_instant("2025-12-31", 1_600 * M)),
            },
        },
    }


def test_ifrs_20f_annual_reads_ebit_da_debt_income_equity() -> None:
    metric = ttm_from_facts(_annual_payload())
    assert metric is not None
    assert metric.as_of == date(2025, 12, 31)
    assert metric.revenue == Decimal(1_600 * M)
    assert metric.ebit == Decimal(600 * M)
    assert metric.ebitda == Decimal(1_000 * M)
    assert metric.fcf == Decimal(-100 * M)
    # Borrowings minus cash; IFRS 16 lease liabilities stay out of debt.
    assert metric.net_debt == Decimal(750 * M)
    assert metric.shares == Decimal(100 * M)
    # Parent-attributable lines win over the consolidated totals.
    assert metric.net_income == Decimal(450 * M)
    assert metric.equity == Decimal(1_600 * M)
    assert usable_ttm(metric)


def test_ifrs_20f_annual_is_not_a_quarterly_ttm() -> None:
    """The refresh requires quarters; a 20-F-only filer gets its TTM from Yahoo instead."""
    assert ttm_from_facts(_annual_payload(), require_quarters=True) is None
    assert ttm_history_from_facts(_annual_payload(), require_quarters=True) == []


def test_tagged_6k_quarters_build_a_ttm() -> None:
    """Some foreign filers (DLO) tag 6-K quarters; with the prior 20-F they make a TTM."""
    revenue = _usd(
        _flow("2025-07-01", "2025-09-30", 300 * M, "6-K"),
        _flow("2025-04-01", "2025-06-30", 280 * M, "6-K"),
        _flow("2025-01-01", "2025-03-31", 260 * M, "6-K"),
        _flow("2024-10-01", "2024-12-31", 240 * M, "20-F"),
    )
    payload = {"cik": 1846832, "facts": {"ifrs-full": {"Revenue": revenue}}}
    metric = ttm_from_facts(payload, require_quarters=True)
    assert metric is not None
    assert metric.as_of == date(2025, 9, 30)
    assert metric.revenue == Decimal(1_080 * M)
