from datetime import date
from decimal import Decimal

from analytics.quant import score_quant
from store.canonical import MetricFy
from store.catalog import GemsConfig

GEMS = GemsConfig()


def _fy(
    day: str,
    *,
    revenue: Decimal = Decimal("200"),
    total_assets: Decimal = Decimal("400"),
    long_term_debt: Decimal = Decimal("40"),
    equity: Decimal = Decimal("280"),
) -> MetricFy:
    as_of = date.fromisoformat(day)
    return MetricFy(
        cik="1",
        as_of=as_of,
        fiscal_year=as_of.year,
        revenue=revenue,
        net_income=Decimal("20"),
        cfo=Decimal("30"),
        gross_profit=Decimal("80"),
        ebit=Decimal("25"),
        total_assets=total_assets,
        current_assets=Decimal("150"),
        current_liabilities=Decimal("70"),
        long_term_debt=long_term_debt,
        total_liabilities=Decimal("120"),
        retained_earnings=Decimal("90"),
        equity=equity,
        shares=Decimal("50"),
    )


def _years() -> list[MetricFy]:
    return [
        _fy("2022-12-31", revenue=Decimal("140"), total_assets=Decimal("320")),
        _fy("2023-12-31", revenue=Decimal("160"), total_assets=Decimal("350")),
        _fy(
            "2024-12-31",
            revenue=Decimal("200"),
            long_term_debt=Decimal("40"),
            equity=Decimal("280"),
        ),
    ]


def test_score_quant_flags_gem_inside_band() -> None:
    row = score_quant(
        _years(),
        price=Decimal("20"),
        shares=Decimal("40000000"),
        fcf=Decimal("80000000"),
        ev=Decimal("1000000000"),
        ttm_revenue=Decimal("400000000"),
        gems=GEMS,
    )
    assert row is not None
    assert row.market_cap == Decimal("800000000.00")
    assert row.is_gem_candidate is True


def test_score_quant_rejects_gem_outside_cap_or_growth() -> None:
    mega = score_quant(
        _years(),
        price=Decimal("200"),
        shares=Decimal("40000000"),
        fcf=Decimal("80000000"),
        ev=Decimal("1000000000"),
        ttm_revenue=Decimal("400000000"),
        gems=GEMS,
    )
    assert mega is not None
    assert mega.is_gem_candidate is False
    flat = score_quant(
        [
            _fy("2023-12-31", revenue=Decimal("200")),
            _fy("2024-12-31", revenue=Decimal("200")),
        ],
        price=Decimal("20"),
        shares=Decimal("40000000"),
        fcf=Decimal("80000000"),
        ev=Decimal("1000000000"),
        ttm_revenue=Decimal("400000000"),
        gems=GEMS,
    )
    assert flat is not None
    assert flat.is_gem_candidate is False


def test_score_quant_empty_years() -> None:
    assert (
        score_quant(
            [],
            price=Decimal("1"),
            shares=Decimal("1"),
            fcf=None,
            ev=None,
            ttm_revenue=None,
            gems=GEMS,
        )
        is None
    )
