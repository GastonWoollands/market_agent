"""Tests for regime detection analytics."""

from datetime import date
from decimal import Decimal

from analytics.regime_detect import (
    _classify_growth,
    _classify_inflation,
    _classify_policy,
    _classify_volatility,
)


def test_growth_slowdown_moderate_payrolls():
    """Slowdown regime from moderate payrolls."""
    payrolls = [
        (date(2026, 4, 1), Decimal("170")),
        (date(2026, 5, 1), Decimal("190")),
        (date(2026, 6, 1), Decimal("200")),
        (date(2026, 7, 1), Decimal("180")),
        (date(2026, 8, 1), Decimal("220")),  # 3m avg = 200k
    ]
    unrate = [
        (date(2026, 4, 1), Decimal("4.0")),
        (date(2026, 5, 1), Decimal("3.9")),
        (date(2026, 6, 1), Decimal("3.8")),
        (date(2026, 7, 1), Decimal("3.8")),
        (date(2026, 8, 1), Decimal("3.8")),
    ]

    regime, confidence, metrics = _classify_growth(payrolls, unrate)

    assert regime in ("expansion", "slowdown")
    assert confidence >= 0.5


def test_growth_recession_weak_payrolls():
    """Recession regime from weak payrolls and rising unemployment."""
    payrolls = [
        (date(2026, 5, 1), Decimal("100")),
        (date(2026, 6, 1), Decimal("40")),
        (date(2026, 7, 1), Decimal("30")),
        (date(2026, 8, 1), Decimal("20")),
    ]
    unrate = [
        (date(2026, 5, 1), Decimal("3.8")),
        (date(2026, 6, 1), Decimal("4.0")),
        (date(2026, 7, 1), Decimal("4.3")),
        (date(2026, 8, 1), Decimal("4.5")),
    ]

    regime, confidence, metrics = _classify_growth(payrolls, unrate)

    assert regime == "recession"
    assert confidence > 0.7
    assert metrics["payroll_3m_avg_k"] < 50
    assert metrics["unrate_change_pp"] > 0.3


def test_inflation_accelerating_mom_rising():
    """Accelerating inflation from consecutive MoM increases."""
    core_pce = [
        (date(2026, 5, 1), Decimal("126.50")),
        (date(2026, 6, 1), Decimal("126.75")),  # +0.20% MoM
        (date(2026, 7, 1), Decimal("127.05")),  # +0.24% MoM
        (date(2026, 8, 1), Decimal("127.40")),  # +0.28% MoM
    ]

    regime, confidence, metrics = _classify_inflation(core_pce)

    assert regime == "accelerating"
    assert confidence > 0.7
    assert len(metrics["recent_mom_pct"]) == 3
    assert metrics["recent_mom_pct"][1] > metrics["recent_mom_pct"][0]
    assert metrics["recent_mom_pct"][2] > metrics["recent_mom_pct"][1]


def test_inflation_decelerating_mom_falling():
    """Decelerating inflation from consecutive MoM decreases."""
    core_pce = [
        (date(2026, 5, 1), Decimal("127.40")),
        (date(2026, 6, 1), Decimal("127.55")),  # +0.12% MoM
        (date(2026, 7, 1), Decimal("127.65")),  # +0.08% MoM
        (date(2026, 8, 1), Decimal("127.70")),  # +0.04% MoM
    ]

    regime, confidence, metrics = _classify_inflation(core_pce)

    assert regime == "decelerating"
    assert confidence > 0.7


def test_policy_tightening_fed_funds_rising():
    """Tightening regime from Fed funds increases."""
    dff = [
        (date(2026, 5, 1), Decimal("3.50")),
        (date(2026, 6, 1), Decimal("3.75")),  # +25bp
        (date(2026, 7, 1), Decimal("4.00")),  # +25bp
        (date(2026, 8, 1), Decimal("4.25")),  # +25bp
    ]

    regime, confidence, metrics = _classify_policy(dff)

    assert regime == "tightening"
    assert confidence > 0.7
    assert all(c > 10 for c in metrics["recent_dff_changes_bp"])


def test_policy_easing_fed_funds_falling():
    """Easing regime from Fed funds decreases."""
    dff = [
        (date(2026, 5, 1), Decimal("4.25")),
        (date(2026, 6, 1), Decimal("4.00")),  # -25bp
        (date(2026, 7, 1), Decimal("3.75")),  # -25bp
        (date(2026, 8, 1), Decimal("3.50")),  # -25bp
    ]

    regime, confidence, metrics = _classify_policy(dff)

    assert regime == "easing"
    assert confidence > 0.7


def test_volatility_suppressed_low_vix():
    """Suppressed volatility from low VIX percentile."""
    from datetime import timedelta
    
    base = date(2026, 8, 30)
    vix = [
        (base - timedelta(days=504 - i), Decimal("14.0"))  # All at 14
        for i in range(503)
    ]
    vix.append((base, Decimal("13.0")))  # Current at 13

    regime, confidence, metrics = _classify_volatility(vix)

    assert regime == "suppressed"
    assert confidence > 0.7
    assert metrics["current_vix"] < 15


def test_volatility_elevated_high_vix():
    """Elevated volatility from high VIX percentile."""
    from datetime import timedelta
    
    base = date(2026, 8, 30)
    vix = [
        (base - timedelta(days=504 - i), Decimal("15.0" if i < 500 else "28.0"))
        for i in range(504)
    ]

    regime, confidence, metrics = _classify_volatility(vix)

    assert regime == "elevated"
    assert confidence > 0.7
    assert metrics["current_vix"] > 25
    assert metrics["percentile_2y"] > 0.75
