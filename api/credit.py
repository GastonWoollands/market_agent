"""Credit curve: ICE BofA OAS and effective yield by rating bucket, read from stored FRED.

Market context for the Ticker page. No vendor calls; `ingest_fred` owns the series.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from api.schemas import CreditBucket, CreditCurveResponse
from store.repos import macro_observations

# (rating, grade, OAS series, effective-yield series)
BUCKETS: tuple[tuple[str, str, str, str], ...] = (
    ("AAA", "IG", "BAMLC0A1CAAA", "BAMLC0A1CAAAEY"),
    ("AA", "IG", "BAMLC0A2CAA", "BAMLC0A2CAAEY"),
    ("A", "IG", "BAMLC0A3CA", "BAMLC0A3CAEY"),
    ("BBB", "IG", "BAMLC0A4CBBB", "BAMLC0A4CBBBEY"),
    ("BB", "HY", "BAMLH0A1HYBB", "BAMLH0A1HYBBEY"),
    ("B", "HY", "BAMLH0A2HYB", "BAMLH0A2HYBEY"),
    ("CCC", "HY", "BAMLH0A3HYC", "BAMLH0A3HYCEY"),
)
GAUGES = ("BAA10Y", "NFCI", "STLFSI4")
HISTORY_DAYS = 400
STALE_AFTER_DAYS = 5

Points = Sequence[tuple[date, Decimal | float]]


def build_credit_curve(series: Mapping[str, Points], *, today: date) -> CreditCurveResponse:
    buckets: list[CreditBucket] = []
    as_of: date | None = None
    for rating, grade, oas_id, yield_id in BUCKETS:
        oas = series.get(oas_id, [])
        yields = series.get(yield_id, [])
        last = _last(oas)
        if last is not None:
            as_of = last[0] if as_of is None else max(as_of, last[0])
        buckets.append(
            CreditBucket(
                rating=rating,
                grade=grade,
                oas_bp=_bp(last),
                oas_1m_bp=_bp(_on_or_before(oas, last, days=30)),
                oas_1y_bp=_bp(_on_or_before(oas, last, days=365)),
                yield_pct=_value(_last(yields)),
                yield_1y_pct=_value(_on_or_before(yields, _last(yields), days=365)),
            )
        )
    nfci = _last(series.get("NFCI", []))
    stlfsi = _last(series.get("STLFSI4", []))
    return CreditCurveResponse(
        stale=as_of is None or (today - as_of).days > STALE_AFTER_DAYS,
        as_of=as_of,
        buckets=buckets,
        baa_10y_bp=_bp(_last(series.get("BAA10Y", []))),
        nfci=_value(nfci),
        nfci_as_of=nfci[0] if nfci else None,
        stlfsi=_value(stlfsi),
        stlfsi_as_of=stlfsi[0] if stlfsi else None,
    )


def load_credit_series(db: Any, *, today: date) -> dict[str, list[tuple[date, Decimal]]]:
    start = today - timedelta(days=HISTORY_DAYS)
    ids = [code for _, _, oas, ey in BUCKETS for code in (oas, ey)] + list(GAUGES)
    return {code: macro_observations(db, code, start=start) for code in ids}


def _last(points: Points) -> tuple[date, Decimal | float] | None:
    return points[-1] if points else None


def _on_or_before(
    points: Points, last: tuple[date, Decimal | float] | None, *, days: int
) -> tuple[date, Decimal | float] | None:
    """Latest point at least `days` before the last one; None when history is shorter."""
    if last is None:
        return None
    cutoff = last[0] - timedelta(days=days)
    found = None
    for point in points:
        if point[0] > cutoff:
            break
        found = point
    return found


def _value(point: tuple[date, Decimal | float] | None) -> float | None:
    return None if point is None else float(point[1])


def _bp(point: tuple[date, Decimal | float] | None) -> float | None:
    """FRED quotes spreads in percent; the desk reads basis points."""
    return None if point is None else round(float(point[1]) * 100, 1)
