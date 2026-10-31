"""Equity-implied credit bucket: Merton / KMV distance to default placed on rating anchors.

Northstar §9. Inputs are stored facts: market cap, 1y equity vol from adjusted closes,
a default point from the latest 10-Q / 10-K liabilities, and the 1y Treasury yield.

- Default point F = (current liabilities − current deferred revenue) + ½ non-current
  liabilities. Deferred revenue is a service obligation, not a claim that forces default.
- Merton: solve E = V·N(d1) − F·e^(−rT)·N(d2) and σE·E = N(d1)·σA·V for (V, σA);
  DD = (ln(V/F) + (r − σA²/2)T) / (σA√T). T = 1.
- Raw N(−DD) prices investment grade at ~0bp (credit-spread puzzle), so DD is never
  turned into a spread directly. It is placed between the median DD of each rating
  bucket in a reviewed calibration set, and the bp shown is that bucket's market OAS.

Stdlib only. Floats inside, the job casts to Decimal.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from analytics.corr import daily_returns
from analytics.risk import MIN_OBS_YEAR, YEAR, realized_vol

BUCKETS = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC")
# (bucket, grade, ICE BofA OAS series, effective-yield series) on FRED.
OAS_SERIES: tuple[tuple[str, str, str, str], ...] = (
    ("AAA", "IG", "BAMLC0A1CAAA", "BAMLC0A1CAAAEY"),
    ("AA", "IG", "BAMLC0A2CAA", "BAMLC0A2CAAEY"),
    ("A", "IG", "BAMLC0A3CA", "BAMLC0A3CAEY"),
    ("BBB", "IG", "BAMLC0A4CBBB", "BAMLC0A4CBBBEY"),
    ("BB", "HY", "BAMLH0A1HYBB", "BAMLH0A1HYBBEY"),
    ("B", "HY", "BAMLH0A2HYB", "BAMLH0A2HYBEY"),
    ("CCC", "HY", "BAMLH0A3HYC", "BAMLH0A3HYCEY"),
)
HORIZON_YEARS = 1.0
MAX_ITER = 200
MAX_CLOSE_AGE_DAYS = 10
MAX_STATEMENT_AGE_DAYS = 400
TOLERANCE = 1e-9

Position = Literal["above", "within", "below"]


@dataclass(frozen=True)
class MertonFit:
    asset_value: float
    vol_asset: float
    dd: float


@dataclass(frozen=True)
class Anchor:
    bucket: str
    median_dd: float
    names: int
    oas_bp: float | None


@dataclass(frozen=True)
class Placement:
    """`bucket` is the nearest anchor; `position` says whether DD sits beyond the ends."""

    bucket: str
    position: Position
    oas_bp: float | None


def default_point(
    current_liabilities: float | None,
    total_liabilities: float | None,
    deferred_revenue_current: float | None = None,
) -> float | None:
    if current_liabilities is None or total_liabilities is None:
        return None
    short = current_liabilities - (deferred_revenue_current or 0.0)
    point = max(short, 0.0) + 0.5 * max(total_liabilities - current_liabilities, 0.0)
    return point if point > 0 else None


def merton(equity: float, point: float, vol_equity: float, risk_free: float) -> MertonFit | None:
    """Fixed-point solve for asset value and asset vol. None when inputs cannot solve."""
    if equity <= 0 or point <= 0 or vol_equity <= 0:
        return None
    t = HORIZON_YEARS
    root_t = math.sqrt(t)
    discounted = point * math.exp(-risk_free * t)
    value = equity + discounted
    vol = vol_equity * equity / value
    for _ in range(MAX_ITER):
        d1 = (math.log(value / point) + (risk_free + vol**2 / 2) * t) / (vol * root_t)
        d2 = d1 - vol * root_t
        n1 = _cdf(d1)
        if n1 <= 0:
            return None
        next_value = (equity + discounted * _cdf(d2)) / n1
        next_vol = vol_equity * equity / (n1 * next_value)
        done = abs(next_value - value) <= TOLERANCE * value and abs(next_vol - vol) <= TOLERANCE
        value, vol = next_value, next_vol
        if done:
            break
    if not (math.isfinite(value) and math.isfinite(vol)) or value <= 0 or vol <= 0:
        return None
    dd = (math.log(value / point) + (risk_free - vol**2 / 2) * t) / (vol * root_t)
    return MertonFit(asset_value=value, vol_asset=vol, dd=dd)


def anchors(samples: Sequence[tuple[str, float]], oas_bp: Mapping[str, float]) -> list[Anchor]:
    """Median DD per bucket, forced monotone so a better bucket never anchors lower."""
    out: list[Anchor] = []
    ceiling = math.inf
    for bucket in BUCKETS:
        values = [dd for name_bucket, dd in samples if name_bucket == bucket]
        if not values:
            continue
        ceiling = min(ceiling, statistics.median(values))
        out.append(Anchor(bucket, ceiling, len(values), oas_bp.get(bucket)))
    return out


def place(dd: float, ladder: Sequence[Anchor]) -> Placement | None:
    """Nearest anchor on the DD axis. Beyond the best or worst anchor reads above / below."""
    if not ladder:
        return None
    top, bottom = ladder[0], ladder[-1]
    if dd > top.median_dd:
        return Placement(top.bucket, "above", top.oas_bp)
    if dd < bottom.median_dd:
        return Placement(bottom.bucket, "below", bottom.oas_bp)
    for upper, lower in zip(ladder, ladder[1:], strict=False):
        if lower.median_dd <= dd <= upper.median_dd:
            span = upper.median_dd - lower.median_dd
            nearer = upper if span == 0 or (upper.median_dd - dd) <= span / 2 else lower
            return Placement(nearer.bucket, "within", nearer.oas_bp)
    return Placement(bottom.bucket, "within", bottom.oas_bp)


@dataclass(frozen=True)
class CreditInputs:
    """Everything one name needs, already as floats."""

    close_as_of: date
    statement_as_of: date
    market_cap: float
    point: float
    vol_equity: float


def credit_inputs(
    closes: list[tuple[date, Decimal]],
    adj: list[tuple[date, Decimal]],
    ttm: Any | None,
    *,
    today: date,
) -> tuple[CreditInputs | None, str | None]:
    """Inputs or the reason they are missing (shown on the Ticker page)."""
    if ttm is None:
        return None, "no SEC TTM row"
    if not closes:
        return None, "no stored daily bars"
    close_as_of, close = closes[-1]
    if (today - close_as_of).days > MAX_CLOSE_AGE_DAYS:
        return None, f"last close {close_as_of} is stale"
    statement_as_of = ttm.as_of
    if (today - statement_as_of).days > MAX_STATEMENT_AGE_DAYS:
        return None, f"balance sheet {statement_as_of} is stale"
    shares = ttm.shares
    point = default_point(
        _float(ttm.current_liabilities),
        _float(ttm.total_liabilities),
        _float(ttm.deferred_revenue_current),
    )
    if not shares or point is None:
        return None, "liabilities or shares not tagged in the latest filing"
    values = [float(value) for _day, value in adj[-(YEAR + 1) :] if value and float(value) > 0]
    vol = realized_vol(daily_returns(values), min_obs=MIN_OBS_YEAR)
    if vol is None:
        return None, "under 180 sessions of adjusted closes"
    return (
        CreditInputs(
            close_as_of=close_as_of,
            statement_as_of=statement_as_of,
            market_cap=float(close) * float(shares),
            point=point,
            vol_equity=vol,
        ),
        None,
    )


def _float(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
