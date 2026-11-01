"""Credit reads for the Ticker page: the FRED rating curve and the equity-implied bucket.

No vendor calls. `ingest_fred` owns the curve, `compute_credit` the stored buckets and ladder.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from analytics.credit import BUCKETS as BUCKETS_ORDER
from analytics.credit import OAS_SERIES, Anchor, CreditInputs, credit_inputs, merton, place
from api.schemas import (
    AgencyRating,
    CreditAnchorRow,
    CreditBucket,
    CreditCurveResponse,
    TickerCredit,
)
from store.catalog import CreditCalibrationFile, load_credit_calibration
from store.repos import latest_credit_anchors, latest_credit_implied, macro_observations

BUCKETS = OAS_SERIES
GAUGES = ("BAA10Y", "NFCI", "STLFSI4")
RISK_FREE_SERIES = "DGS1"
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


def build_ticker_credit(
    *,
    ticker: str,
    sector: str | None,
    stored: Any | None,
    inputs: CreditInputs | None,
    reason: str | None,
    ladder: Sequence[Any],
    risk_free: float | None,
    calibration: CreditCalibrationFile,
) -> TickerCredit:
    """Stored row when there is one, else read-time on the stored ladder (names outside the job)."""
    rated = calibration.by_ticker().get(ticker)
    agency = (
        AgencyRating(
            rating=rated.rating,
            bucket=rated.bucket,
            agency=rated.agency,
            as_of=rated.as_of,
            source=rated.source,
        )
        if rated is not None
        else None
    )
    # Best bucket first. Monotone capping can tie two medians, so order by bucket, not DD.
    rungs = sorted(
        (
            Anchor(row.bucket, float(row.median_dd), int(row.names), _opt(row.oas_bp))
            for row in ladder
        ),
        key=lambda row: BUCKETS_ORDER.index(row.bucket),
    )
    base = TickerCredit(
        agency=agency,
        anchors=[
            CreditAnchorRow(
                bucket=row.bucket, median_dd=row.median_dd, names=row.names, oas_bp=row.oas_bp
            )
            for row in rungs
        ],
    )
    if sector in calibration.exclude_sectors or ticker in calibration.exclude_tickers:
        base.unavailable = (
            f"Not scored: {sector or ticker} liabilities are funding, float or custody, "
            "not claims that force default."
        )
        return base
    if stored is not None:
        return base.model_copy(
            update={
                "source": "stored",
                "as_of": stored.as_of,
                "statement_as_of": stored.statement_as_of,
                "market_cap": float(stored.market_cap),
                "default_point": float(stored.default_point),
                "vol_equity": float(stored.vol_equity),
                "asset_value": float(stored.asset_value),
                "vol_asset": float(stored.vol_asset),
                "risk_free": float(stored.risk_free),
                "dd": float(stored.dd),
                "bucket": stored.bucket,
                "position": stored.position,
                "bucket_oas_bp": _opt(stored.bucket_oas_bp),
                "calibration_version": stored.calibration_version,
            }
        )
    if inputs is None:
        base.unavailable = f"Not computed: {reason or 'inputs missing'}."
        return base
    if not rungs or risk_free is None:
        base.unavailable = "Not computed: no calibration ladder stored. Run compute_credit."
        return base
    fit = merton(inputs.market_cap, inputs.point, inputs.vol_equity, risk_free)
    placement = place(fit.dd, rungs) if fit is not None else None
    if fit is None or placement is None:
        base.unavailable = "Not computed: the Merton solve did not converge."
        return base
    return base.model_copy(
        update={
            "source": "read_time",
            "as_of": inputs.close_as_of,
            "statement_as_of": inputs.statement_as_of,
            "market_cap": inputs.market_cap,
            "default_point": inputs.point,
            "vol_equity": inputs.vol_equity,
            "asset_value": fit.asset_value,
            "vol_asset": fit.vol_asset,
            "risk_free": risk_free,
            "dd": fit.dd,
            "bucket": placement.bucket,
            "position": placement.position,
            "bucket_oas_bp": placement.oas_bp,
            "calibration_version": calibration.version,
        }
    )


def load_ticker_credit(db: Any, item: Any, *, today: date) -> TickerCredit:
    """Credit block for one Ticker page (`item` is `api.ticker.NameInputs`)."""
    instrument = item.instrument
    stored = latest_credit_implied(db, [instrument.id]).get(instrument.id)
    closes = [(day, Decimal(str(value))) for day, value in item.closes]
    adj = [(day, Decimal(str(value))) for day, value in item.adj_closes]
    inputs, reason = credit_inputs(closes, adj, item.ttm[-1] if item.ttm else None, today=today)
    rate = macro_observations(db, RISK_FREE_SERIES, start=today - timedelta(days=30))
    return build_ticker_credit(
        ticker=instrument.ticker,
        sector=instrument.sector,
        stored=stored,
        inputs=inputs,
        reason=reason,
        ladder=latest_credit_anchors(db),
        risk_free=float(rate[-1][1]) / 100 if rate else None,
        calibration=load_credit_calibration(),
    )


def _opt(value: Any) -> float | None:
    return None if value is None else float(value)
