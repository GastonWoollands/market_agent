from datetime import date
from decimal import Decimal

from analytics.piotroski import piotroski
from store.canonical import MetricFy

CIK = "0000320193"


def _fy(
    day: str,
    *,
    revenue: int,
    net_income: int,
    cfo: int,
    gross_profit: int,
    total_assets: int,
    current_assets: int,
    current_liabilities: int,
    long_term_debt: int,
    shares: int,
) -> MetricFy:
    as_of = date.fromisoformat(day)
    return MetricFy(
        cik=CIK,
        as_of=as_of,
        fiscal_year=as_of.year,
        revenue=Decimal(revenue),
        net_income=Decimal(net_income),
        cfo=Decimal(cfo),
        gross_profit=Decimal(gross_profit),
        ebit=Decimal(net_income),
        total_assets=Decimal(total_assets),
        current_assets=Decimal(current_assets),
        current_liabilities=Decimal(current_liabilities),
        long_term_debt=Decimal(long_term_debt),
        total_liabilities=Decimal(current_liabilities + long_term_debt),
        retained_earnings=Decimal(net_income),
        equity=Decimal(total_assets - current_liabilities - long_term_debt),
        shares=Decimal(shares),
    )


def _three_improving() -> list[MetricFy]:
    return [
        _fy(
            "2022-12-31",
            revenue=350,
            net_income=50,
            cfo=60,
            gross_profit=130,
            total_assets=1000,
            current_assets=250,
            current_liabilities=140,
            long_term_debt=220,
            shares=100,
        ),
        _fy(
            "2023-12-31",
            revenue=400,
            net_income=80,
            cfo=90,
            gross_profit=160,
            total_assets=1100,
            current_assets=300,
            current_liabilities=150,
            long_term_debt=200,
            shares=100,
        ),
        _fy(
            "2024-12-31",
            revenue=500,
            net_income=120,
            cfo=150,
            gross_profit=220,
            total_assets=1200,
            current_assets=400,
            current_liabilities=160,
            long_term_debt=180,
            shares=100,
        ),
    ]


def test_piotroski_nine_when_all_tests_pass() -> None:
    result = piotroski(_three_improving())
    assert result.score == 9
    assert result.tests["complete"] is True
    assert result.tests["accrual"] is True
    assert result.tests["no_dilution"] is True
    assert result.tests["roa_base"] == "beginning"


def test_piotroski_incomplete_without_third_year() -> None:
    result = piotroski(_three_improving()[1:])
    assert result.score is None
    assert result.tests["complete"] is False
    assert result.tests["delta_roa"] is None
    assert result.tests["delta_turnover"] is None


def test_piotroski_one_year_is_not_zero() -> None:
    result = piotroski(_three_improving()[-1:])
    assert result.score is None
    assert result.tests["reason"] == "need_two_years"


def test_piotroski_accrual_is_cfo_gt_net_income() -> None:
    years = _three_improving()
    weak = years[-1].model_copy(update={"cfo": Decimal("100")})
    result = piotroski([*years[:-1], weak])
    assert result.score == 8
    assert result.tests["accrual"] is False


def test_piotroski_dilution_and_leverage_fail() -> None:
    years = _three_improving()
    weak = years[-1].model_copy(
        update={"shares": Decimal("120"), "long_term_debt": Decimal("400")}
    )
    result = piotroski([*years[:-1], weak])
    assert result.score == 7
    assert result.tests["no_dilution"] is False
    assert result.tests["delta_leverage"] is False
