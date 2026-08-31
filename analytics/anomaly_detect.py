"""
Market anomaly detection from cross-asset relationships.

Detects unusual market behavior:
1. Correlation breakdowns (SPY vs 10Y moving contrary to historical pattern)
2. Z-score extremes (series moving >2 standard deviations)
3. Breadth divergences (SPY up while small caps down)

No vendor I/O - operates on stored series only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import correlation, fmean, pstdev

Series = Sequence[tuple[date, float]]


@dataclass(frozen=True)
class Anomaly:
    """Market anomaly with severity scoring."""

    type: str
    description: str
    severity: float
    components: dict


def detect_anomalies(series_map: Mapping[str, Series], as_of: date) -> list[Anomaly]:
    """
    Detect unusual cross-asset moves and relationship breakdowns.

    Args:
        series_map: Dict of series_id -> [(date, value), ...]
        as_of: Date to analyze

    Returns:
        List of Anomaly objects sorted by severity (high to low)
    """
    anomalies = []

    _detect_correlation_breaks(series_map, anomalies)
    _detect_z_score_extremes(series_map, anomalies)
    _detect_breadth_divergence(series_map, anomalies)

    anomalies.sort(key=lambda a: a.severity, reverse=True)
    return anomalies[:3]


def _detect_correlation_breaks(
    series_map: Mapping[str, Series], anomalies: list[Anomaly]
) -> None:
    """
    Detect SPY vs 10Y correlation breakdowns.

    Historically SPY and DGS10 are negatively correlated (rates up, stocks down).
    Anomaly when both move same direction with magnitude.
    """
    spy_series = series_map.get("SPY")
    dgs10_series = series_map.get("DGS10")

    if not spy_series or not dgs10_series or len(spy_series) < 20:
        return

    spy_change = spy_series[-1][1] - spy_series[-2][1] if len(spy_series) > 1 else 0
    dgs10_change = dgs10_series[-1][1] - dgs10_series[-2][1] if len(dgs10_series) > 1 else 0

    window = min(60, len(spy_series) - 1)
    spy_returns = [spy_series[i][1] - spy_series[i - 1][1] for i in range(-window, 0)]
    dgs10_returns = [dgs10_series[i][1] - dgs10_series[i - 1][1] for i in range(-window, 0)]

    if len(spy_returns) != len(dgs10_returns) or len(spy_returns) < 20:
        return

    hist_corr = correlation(spy_returns, dgs10_returns)

    if hist_corr < -0.3:
        if (spy_change > 0.5 and dgs10_change > 0.05) or (
            spy_change < -0.5 and dgs10_change < -0.05
        ):
            desc = (
                f"SPY {spy_change:+.1%} with 10Y {dgs10_change*100:+.0f}bp "
                f"(historical correlation {hist_corr:.2f})"
            )
            anomalies.append(
                Anomaly(
                    type="correlation_break",
                    description=desc,
                    severity=0.75,
                    components={
                        "spy_change_pct": round(spy_change, 3),
                        "dgs10_change_bp": round(dgs10_change * 100, 1),
                        "hist_corr": round(hist_corr, 2),
                    },
                )
            )


def _detect_z_score_extremes(
    series_map: Mapping[str, Series], anomalies: list[Anomaly]
) -> None:
    """Detect extreme moves (>2 standard deviations) in any series."""
    for series_id, series in series_map.items():
        if len(series) < 60:
            continue

        recent_changes = [series[i][1] - series[i - 1][1] for i in range(-60, 0)]
        if not recent_changes:
            continue

        today_change = series[-1][1] - series[-2][1] if len(series) > 1 else 0
        mean_change = fmean(recent_changes)
        std_change = pstdev(recent_changes)

        if std_change > 0:
            z_score = (today_change - mean_change) / std_change
            if abs(z_score) > 2.0:
                anomalies.append(
                    Anomaly(
                        type="z_score_extreme",
                        description=f"{series_id} moved {z_score:.1f} standard deviations",
                        severity=min(abs(z_score) / 3.0, 1.0),
                        components={
                            "series_id": series_id,
                            "z_score": round(z_score, 2),
                            "change": round(today_change, 4),
                        },
                    )
                )


def _detect_breadth_divergence(
    series_map: Mapping[str, Series], anomalies: list[Anomaly]
) -> None:
    """
    Detect breadth divergence (SPY up while equal weight / small caps down).

    Indicates narrow leadership, often precedes corrections.
    """
    spy_series = series_map.get("SPY")
    rsp_series = series_map.get("RSP")
    iwm_series = series_map.get("IWM")

    if not spy_series or not rsp_series or not iwm_series:
        return

    spy_chg = spy_series[-1][1] - spy_series[-2][1] if len(spy_series) > 1 else 0
    rsp_chg = rsp_series[-1][1] - rsp_series[-2][1] if len(rsp_series) > 1 else 0
    iwm_chg = iwm_series[-1][1] - iwm_series[-2][1] if len(iwm_series) > 1 else 0

    if spy_chg > 0.5 and rsp_chg < 0 and iwm_chg < 0:
        desc = (
            f"SPY +{spy_chg:.1%} while RSP {rsp_chg:+.1%}, "
            f"IWM {iwm_chg:+.1%} (narrow leadership)"
        )
        anomalies.append(
            Anomaly(
                type="breadth_divergence",
                description=desc,
                severity=0.60,
                components={
                    "spy_pct": round(spy_chg, 3),
                    "rsp_pct": round(rsp_chg, 3),
                    "iwm_pct": round(iwm_chg, 3),
                },
            )
        )
