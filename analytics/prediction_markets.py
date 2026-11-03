"""Kalshi contract reads: quote mids and the implied distribution of an index close.

Kalshi books are thin outside the money; a contract with no bid carries no probability.
The UI labels everything here market-implied, not a forecast.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from store.canonical import KalshiMarket

# A book whose quoted mids sum below this is too thin to read as a distribution.
MIN_QUOTED_MASS = 0.8
MIN_QUOTED_BUCKETS = 3


def contract_mid(market: KalshiMarket) -> float | None:
    """Mid of the yes bid / ask. None when nobody bids (the ask alone is not a price)."""
    if market.yes_bid is None or market.yes_ask is None or market.yes_bid <= 0:
        return None
    return float(market.yes_bid + market.yes_ask) / 2


@dataclass(frozen=True)
class Bucket:
    low: float
    high: float
    probability: float


@dataclass(frozen=True)
class RangeDistribution:
    """Mutually exclusive close-price buckets normalised to one.

    Open-ended tails get the width of their neighbour so the quantiles stay finite; the
    10/50/90 points interpolate linearly inside a bucket.
    """

    buckets: tuple[Bucket, ...]
    quoted_mass: float
    quoted_buckets: int

    @classmethod
    def from_markets(cls, markets: Sequence[KalshiMarket]) -> RangeDistribution | None:
        edged = [(edges, market) for market in markets if (edges := _edges(market)) is not None]
        edged.sort(key=lambda item: item[0][0] if item[0][0] is not None else float("-inf"))
        if not edged:
            return None
        width = _typical_width([edges for edges, _market in edged])
        mids = [contract_mid(market) for _edges, market in edged]
        mass = sum(mid for mid in mids if mid is not None)
        if mass <= 0 or width is None:
            return None
        buckets = []
        for (low, high), mid in zip((edges for edges, _m in edged), mids, strict=True):
            low = high - width if low is None else low
            high = low + width if high is None else high
            buckets.append(Bucket(low, high, (mid or 0.0) / mass))
        return cls(tuple(buckets), mass, sum(1 for mid in mids if mid is not None))

    @property
    def thin(self) -> bool:
        return self.quoted_mass < MIN_QUOTED_MASS or self.quoted_buckets < MIN_QUOTED_BUCKETS

    @property
    def mode(self) -> Bucket:
        return max(self.buckets, key=lambda bucket: bucket.probability)

    def quantile(self, q: float) -> float:
        cumulative: list[float] = []
        total = 0.0
        for bucket in self.buckets:
            total += bucket.probability
            cumulative.append(total)
        index = min(bisect_left(cumulative, q), len(self.buckets) - 1)
        bucket = self.buckets[index]
        before = cumulative[index - 1] if index else 0.0
        share = (q - before) / bucket.probability if bucket.probability else 0.0
        return bucket.low + share * (bucket.high - bucket.low)


def _edges(market: KalshiMarket) -> tuple[float | None, float | None] | None:
    floor = _edge(market.floor_strike)
    cap = _edge(market.cap_strike)
    if market.strike_type == "between" and floor is not None and cap is not None:
        return floor, cap
    if market.strike_type == "less" and cap is not None:
        return None, cap
    if market.strike_type == "greater" and floor is not None:
        return floor, None
    return None


def _edge(value: Decimal | None) -> float | None:
    """Kalshi writes bucket edges as 7249.9999; index strikes are whole points."""
    return None if value is None else float(value.to_integral_value())


def _typical_width(edges: list[tuple[float | None, float | None]]) -> float | None:
    widths = sorted(high - low for low, high in edges if low is not None and high is not None)
    return widths[len(widths) // 2] if widths else None
