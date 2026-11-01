import math
from datetime import date, timedelta
from decimal import Decimal
from math import isclose
from types import SimpleNamespace

from analytics.credit import (
    Anchor,
    anchors,
    credit_inputs,
    default_point,
    merton,
    place,
)
from api.credit import build_ticker_credit
from store.catalog import CreditCalibrationFile

TODAY = date(2026, 10, 30)
OAS = {"AAA": 46.0, "AA": 65.0, "A": 74.0, "BBB": 110.0, "BB": 194.0, "B": 332.0, "CCC": 1325.0}


def test_default_point_drops_deferred_revenue_and_halves_long_term() -> None:
    assert default_point(100.0, 300.0, 40.0) == 60.0 + 100.0
    assert default_point(100.0, 300.0) == 200.0
    assert default_point(None, 300.0) is None
    assert default_point(0.0, 0.0) is None


def test_merton_satisfies_both_equations() -> None:
    equity, point, vol_e, r = 50.0, 80.0, 0.6, 0.04
    fit = merton(equity, point, vol_e, r)
    assert fit is not None

    def cdf(x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    d1 = (math.log(fit.asset_value / point) + (r + fit.vol_asset**2 / 2)) / fit.vol_asset
    d2 = d1 - fit.vol_asset
    priced = fit.asset_value * cdf(d1) - point * math.exp(-r) * cdf(d2)
    assert isclose(priced, equity, rel_tol=1e-6)
    assert isclose(vol_e * equity, cdf(d1) * fit.vol_asset * fit.asset_value, rel_tol=1e-6)
    assert isclose(fit.dd, d2, rel_tol=1e-9)


def test_more_leverage_or_vol_means_lower_dd() -> None:
    base = merton(100.0, 50.0, 0.3, 0.04).dd
    assert merton(100.0, 150.0, 0.3, 0.04).dd < base
    assert merton(100.0, 50.0, 0.9, 0.04).dd < base
    assert merton(0.0, 50.0, 0.3, 0.04) is None


def test_anchors_are_medians_forced_monotone() -> None:
    samples = [("AA", 9.0), ("AA", 11.0), ("A", 12.0), ("BBB", 4.0), ("BBB", 6.0)]
    ladder = anchors(samples, OAS)
    assert [(row.bucket, row.median_dd, row.names) for row in ladder] == [
        ("AA", 10.0, 2),
        ("A", 10.0, 1),  # median 12 would sit above AA: capped
        ("BBB", 5.0, 2),
    ]


def test_place_nearest_anchor_and_ends() -> None:
    ladder = [
        Anchor("AA", 9.0, 5, 65.0),
        Anchor("BBB", 4.5, 20, 110.0),
        Anchor("CCC", 1.3, 4, 1325.0),
    ]
    assert place(12.0, ladder).position == "above"
    assert place(8.0, ladder).bucket == "AA"
    assert place(5.0, ladder).bucket == "BBB"
    below = place(0.9, ladder)
    assert (below.bucket, below.position, below.oas_bp) == ("CCC", "below", 1325.0)


def _ttm(**kwargs) -> SimpleNamespace:
    row = {
        "as_of": TODAY - timedelta(days=120),
        "shares": Decimal("10"),
        "current_liabilities": Decimal("100"),
        "total_liabilities": Decimal("300"),
        "deferred_revenue_current": None,
    }
    row.update(kwargs)
    return SimpleNamespace(**row)


def _bars(days: int = 260) -> list[tuple[date, Decimal]]:
    return [
        (TODAY - timedelta(days=days - i), Decimal(str(round(50 * (1.01 if i % 2 else 0.99), 4))))
        for i in range(days)
    ]


def test_credit_inputs_and_reasons() -> None:
    bars = _bars()
    inputs, reason = credit_inputs(bars, bars, _ttm(), today=TODAY)
    assert reason is None
    assert inputs.point == 200.0
    assert isclose(inputs.market_cap, float(bars[-1][1]) * 10)
    assert inputs.vol_equity > 0
    _none, why = credit_inputs(bars, bars, _ttm(total_liabilities=None), today=TODAY)
    assert "liabilities" in why
    _none, why = credit_inputs(bars, bars, _ttm(as_of=TODAY - timedelta(days=500)), today=TODAY)
    assert "stale" in why
    _none, why = credit_inputs(bars[:50], bars[:50], _ttm(), today=TODAY + timedelta(days=300))
    assert "stale" in why


def _calibration(**kwargs) -> CreditCalibrationFile:
    raw = {
        "version": "test",
        "exclude_sectors": ["Financials"],
        "exclude_tickers": ["F"],
        "names": [
            {
                "ticker": "ACME",
                "bucket": "BB",
                "rating": "BB+",
                "agency": "S&P",
                "confidence": "high",
            }
        ],
    }
    raw.update(kwargs)
    return CreditCalibrationFile.model_validate(raw)


def test_ticker_credit_read_time_and_exclusions() -> None:
    bars = _bars()
    inputs, _ = credit_inputs(bars, bars, _ttm(), today=TODAY)
    ladder = [
        SimpleNamespace(bucket="AA", median_dd=Decimal("9"), names=5, oas_bp=Decimal("65")),
        SimpleNamespace(bucket="CCC", median_dd=Decimal("1.3"), names=4, oas_bp=Decimal("1325")),
    ]
    credit = build_ticker_credit(
        ticker="ACME",
        sector="Industrials",
        stored=None,
        inputs=inputs,
        reason=None,
        ladder=ladder,
        risk_free=0.044,
        calibration=_calibration(),
    )
    assert credit.source == "read_time"
    assert credit.bucket in {"AA", "CCC"}
    assert credit.agency.rating == "BB+"
    assert [row.bucket for row in credit.anchors] == ["AA", "CCC"]
    bank = build_ticker_credit(
        ticker="BANK",
        sector="Financials",
        stored=None,
        inputs=inputs,
        reason=None,
        ladder=ladder,
        risk_free=0.044,
        calibration=_calibration(),
    )
    assert bank.source is None and "Not scored" in bank.unavailable
    missing = build_ticker_credit(
        ticker="X",
        sector="Industrials",
        stored=None,
        inputs=None,
        reason="no SEC TTM row",
        ladder=ladder,
        risk_free=0.044,
        calibration=_calibration(),
    )
    assert missing.unavailable == "Not computed: no SEC TTM row."
