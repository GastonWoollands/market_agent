from datetime import date
from decimal import Decimal

from analytics.altman import altman
from store.canonical import MetricFy

ROW = MetricFy(
    cik="0000320193",
    as_of=date(2024, 12, 31),
    fiscal_year=2024,
    revenue=Decimal("100"),
    net_income=Decimal("12"),
    cfo=Decimal("15"),
    gross_profit=Decimal("40"),
    ebit=Decimal("15"),
    total_assets=Decimal("100"),
    current_assets=Decimal("40"),
    current_liabilities=Decimal("20"),
    long_term_debt=Decimal("30"),
    total_liabilities=Decimal("50"),
    retained_earnings=Decimal("30"),
    equity=Decimal("50"),
    shares=Decimal("10"),
)


def test_altman_industrial_formula() -> None:
    result = altman(ROW, market_cap=Decimal("80"))
    assert result.inapplicable is False
    assert result.z_score == Decimal("3.1150")
    assert result.components["wc_ta"] == 0.2
    assert result.components["sales_ta"] == 1.0


def test_altman_inapplicable_without_current_accounts() -> None:
    bank = ROW.model_copy(update={"current_assets": None, "current_liabilities": None})
    result = altman(bank, market_cap=Decimal("80"))
    assert result.z_score is None
    assert result.inapplicable is True
    assert result.components["reason"] == "missing_current_accounts"


def test_altman_incomplete_not_inapplicable() -> None:
    missing = ROW.model_copy(update={"retained_earnings": None})
    result = altman(missing, market_cap=Decimal("80"))
    assert result.z_score is None
    assert result.inapplicable is False
    assert result.components["reason"] == "incomplete_inputs"


def test_altman_missing_market_cap_is_incomplete() -> None:
    result = altman(ROW, market_cap=None)
    assert result.z_score is None
    assert result.inapplicable is False
