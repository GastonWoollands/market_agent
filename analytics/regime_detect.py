"""
Macro regime classification from stored FRED data.

Classifies market environment into structured regimes:
- Growth: expansion, slowdown, recession, recovery
- Inflation: accelerating, stable, decelerating
- Policy: tightening, neutral, easing
- Volatility: suppressed, normal, elevated

No vendor I/O - reads from macro_observation table only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean
from typing import TYPE_CHECKING

from analytics.lookback import sort_points

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

Points = Sequence[tuple[date, Decimal]]


@dataclass(frozen=True)
class RegimeComponents:
    """Structured macro regime classification with confidence scores."""

    growth: str
    inflation: str
    policy: str
    volatility: str
    growth_confidence: float
    inflation_confidence: float
    policy_confidence: float
    volatility_confidence: float
    metrics: dict


def classify_regime(session: Session, as_of: date) -> RegimeComponents:
    """
    Compute macro regime classification from stored series.

    Args:
        session: SQLAlchemy session
        as_of: Date to classify

    Returns:
        RegimeComponents with classifications and confidence scores
    """
    from store.repos import load_macro_points

    lookback = as_of - timedelta(days=180)

    payrolls = load_macro_points(session, "PAYEMS", lookback, as_of)
    unrate = load_macro_points(session, "UNRATE", lookback, as_of)
    core_pce = load_macro_points(session, "PCEPILFE", lookback, as_of)
    vix = load_macro_points(session, "VIXCLS", lookback, as_of)
    dff = load_macro_points(session, "DFF", lookback, as_of)

    growth_regime, growth_conf, growth_metrics = _classify_growth(payrolls, unrate)
    inflation_regime, inflation_conf, inflation_metrics = _classify_inflation(core_pce)
    policy_regime, policy_conf, policy_metrics = _classify_policy(dff)
    volatility_regime, volatility_conf, volatility_metrics = _classify_volatility(vix)

    return RegimeComponents(
        growth=growth_regime,
        inflation=inflation_regime,
        policy=policy_regime,
        volatility=volatility_regime,
        growth_confidence=growth_conf,
        inflation_confidence=inflation_conf,
        policy_confidence=policy_conf,
        volatility_confidence=volatility_conf,
        metrics={
            "growth": growth_metrics,
            "inflation": inflation_metrics,
            "policy": policy_metrics,
            "volatility": volatility_metrics,
        },
    )


def _classify_growth(payrolls: Points, unrate: Points) -> tuple[str, float, dict]:
    """
    Growth regime from payrolls and unemployment.

    Logic:
    - expansion: 3m avg payrolls > 150k, unemployment stable/falling
    - slowdown: 3m avg payrolls 50-150k, unemployment rising
    - recession: 3m avg payrolls < 50k, unemployment rising > 0.5pp
    - recovery: payrolls rebounding, unemployment falling

    Returns:
        (regime, confidence, metrics)
    """
    payroll_points = sort_points(payrolls)
    unrate_points = sort_points(unrate)

    if len(payroll_points) < 3 or len(unrate_points) < 3:
        return "unknown", 0.0, {"reason": "insufficient data"}

    recent_changes = [
        float(payroll_points[i][1] - payroll_points[i - 1][1]) for i in range(-3, 0)
    ]
    avg_payroll_change = mean(recent_changes) if recent_changes else None

    current_unrate = float(unrate_points[-1][1])
    prior_unrate = float(unrate_points[-4][1]) if len(unrate_points) >= 4 else current_unrate
    unrate_change = current_unrate - prior_unrate

    if avg_payroll_change is None:
        return "unknown", 0.3, {"payroll_3m_avg_k": None, "unrate_change_pp": unrate_change}

    metrics = {
        "payroll_3m_avg_k": round(avg_payroll_change, 1),
        "unrate_change_pp": round(unrate_change, 2),
    }

    if avg_payroll_change > 150 and unrate_change <= 0.2:
        return "expansion", 0.85, metrics
    if avg_payroll_change < 50 and unrate_change > 0.3:
        return "recession", 0.80, metrics
    if 50 <= avg_payroll_change <= 150 and unrate_change > 0:
        return "slowdown", 0.75, metrics
    if avg_payroll_change > 100 and unrate_change < -0.2:
        return "recovery", 0.70, metrics

    return "slowdown", 0.50, metrics


def _classify_inflation(core_pce_points: Points) -> tuple[str, float, dict]:
    """
    Inflation regime from Core PCE MoM trend.

    Logic:
    - accelerating: MoM rising 3 consecutive months
    - decelerating: MoM falling 3 consecutive months
    - stable: no clear trend

    Returns:
        (regime, confidence, metrics)
    """
    points = sort_points(core_pce_points)

    if len(points) < 4:
        return "unknown", 0.0, {"reason": "insufficient data"}

    mom_values = []
    for i in range(-3, 0):
        if i - 1 >= -len(points):
            current = float(points[i][1])
            prior = float(points[i - 1][1])
            if prior != 0:
                mom_pct = ((current / prior - 1) * 100)
                mom_values.append(mom_pct)

    if len(mom_values) < 3:
        return "unknown", 0.3, {"mom_values": mom_values}

    metrics = {"recent_mom_pct": [round(m, 2) for m in mom_values]}

    if mom_values[1] > mom_values[0] and mom_values[2] > mom_values[1]:
        return "accelerating", 0.80, metrics
    if mom_values[1] < mom_values[0] and mom_values[2] < mom_values[1]:
        return "decelerating", 0.80, metrics

    return "stable", 0.60, metrics


def _classify_policy(dff_points: Points) -> tuple[str, float, dict]:
    """
    Policy regime from Fed funds trend.

    Logic:
    - tightening: Fed funds rising (majority of last 3 changes positive)
    - easing: Fed funds falling (majority of last 3 changes negative)
    - neutral: Fed funds flat

    Returns:
        (regime, confidence, metrics)
    """
    points = sort_points(dff_points)

    if len(points) < 4:
        return "unknown", 0.0, {"reason": "insufficient data"}

    changes = [float(points[i][1] - points[i - 1][1]) for i in range(-3, 0)]

    metrics = {"recent_dff_changes_bp": [round(c * 100, 1) for c in changes]}

    if sum(1 for c in changes if c > 0.05) >= 2:
        return "tightening", 0.75, metrics
    if sum(1 for c in changes if c < -0.05) >= 2:
        return "easing", 0.75, metrics

    return "neutral", 0.70, metrics


def _classify_volatility(vix_points: Points) -> tuple[str, float, dict]:
    """
    Volatility regime from VIX percentile.

    Logic:
    - suppressed: VIX < 25th percentile (2-year)
    - elevated: VIX > 75th percentile (2-year)
    - normal: VIX in middle 50%

    Returns:
        (regime, confidence, metrics)
    """
    points = sort_points(vix_points)

    if len(points) < 20:
        return "unknown", 0.0, {"reason": "insufficient data"}

    current_vix = float(points[-1][1])

    lookback_values = [float(p[1]) for p in points[-504:]]
    lookback_values.sort()
    percentile = sum(1 for v in lookback_values if v < current_vix) / len(lookback_values)

    metrics = {"current_vix": round(current_vix, 1), "percentile_2y": round(percentile, 2)}

    if percentile < 0.25:
        return "suppressed", 0.85, metrics
    if percentile > 0.75:
        return "elevated", 0.85, metrics

    return "normal", 0.80, metrics
