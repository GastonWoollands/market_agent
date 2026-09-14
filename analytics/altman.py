"""Altman Z-Score (industrial formula) from one fiscal-year snapshot + market cap.

Z = 1.2·WC/TA + 1.4·RE/TA + 3.3·EBIT/TA + 0.6·MVE/TL + 1.0·Sales/TA

Inapplicable (typical banks/insurers) when current assets or liabilities are
missing — return z=None and inapplicable=True rather than a fake 3.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from store.canonical import MetricFy

ZERO = Decimal("0")
WC_TA = Decimal("1.2")
RE_TA = Decimal("1.4")
EBIT_TA = Decimal("3.3")
MVE_TL = Decimal("0.6")
SALES_TA = Decimal("1.0")


@dataclass(frozen=True)
class AltmanResult:
    z_score: Decimal | None
    inapplicable: bool
    components: dict[str, Any]


def altman(row: MetricFy, *, market_cap: Decimal | None) -> AltmanResult:
    if row.current_assets is None or row.current_liabilities is None:
        return AltmanResult(
            z_score=None,
            inapplicable=True,
            components={"reason": "missing_current_accounts"},
        )
    ta = row.total_assets
    tl = row.total_liabilities
    if ta is None or ta <= ZERO or tl is None or tl <= ZERO:
        return AltmanResult(
            z_score=None,
            inapplicable=True,
            components={"reason": "missing_assets_or_liabilities"},
        )
    if (
        row.retained_earnings is None
        or row.ebit is None
        or row.revenue is None
        or market_cap is None
        or market_cap <= ZERO
    ):
        return AltmanResult(
            z_score=None,
            inapplicable=False,
            components={"reason": "incomplete_inputs"},
        )
    wc = row.current_assets - row.current_liabilities
    wc_ta = wc / ta
    re_ta = row.retained_earnings / ta
    ebit_ta = row.ebit / ta
    mve_tl = market_cap / tl
    sales_ta = row.revenue / ta
    z_score = (
        WC_TA * wc_ta
        + RE_TA * re_ta
        + EBIT_TA * ebit_ta
        + MVE_TL * mve_tl
        + SALES_TA * sales_ta
    )
    return AltmanResult(
        z_score=z_score.quantize(Decimal("0.0001")),
        inapplicable=False,
        components={
            "wc_ta": float(wc_ta),
            "re_ta": float(re_ta),
            "ebit_ta": float(ebit_ta),
            "mve_tl": float(mve_tl),
            "sales_ta": float(sales_ta),
        },
    )
