"""Equity-implied credit bucket (Merton DD on rating anchors) for valuation + watchlist names.

Reads stored bars, TTM balance-sheet liabilities, FRED DGS1 and the ICE BofA OAS by rating,
plus `config/credit_calibration.yaml`. Writes `credit_implied` and the day's `credit_anchor`
ladder. Run after `ingest_sec`, `ingest_yahoo` and `ingest_fred`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from analytics.credit import (
    OAS_SERIES,
    Anchor,
    CreditInputs,
    MertonFit,
    anchors,
    credit_inputs,
    merton,
    place,
)
from jobs.runtime import record_job
from store.catalog import CreditCalibrationFile, load_credit_calibration
from store.engine import session_scope
from store.repos import (
    adj_closes_for_instrument_ids,
    closes_for_instrument_ids,
    instrument_by_ticker,
    instruments_in_universes,
    latest_metric_ttm_map,
    macro_observations,
    replace_credit_anchors,
    upsert_credit_implied,
)

log = logging.getLogger("jobs.compute_credit")
JOB_NAME = "compute_credit"
UNIVERSES = ("valuation", "watchlist")
LOOKBACK_DAYS = 400
MIN_ANCHOR_NAMES = 2
RISK_FREE_SERIES = "DGS1"


def fit_ladder(
    fits: dict[str, MertonFit],
    calibration: CreditCalibrationFile,
    oas_bp: dict[str, float],
) -> list[Anchor]:
    samples = [
        (item.bucket, fits[item.ticker].dd)
        for item in calibration.names
        if item.fitted and item.ticker in fits
    ]
    return [row for row in anchors(samples, oas_bp) if row.names >= MIN_ANCHOR_NAMES]


def compute(*, today: date | None = None) -> dict[str, object]:
    today = today or date.today()
    calibration = load_credit_calibration()
    excluded_sectors = set(calibration.exclude_sectors)
    excluded_tickers = set(calibration.exclude_tickers)
    start = today - timedelta(days=LOOKBACK_DAYS)
    with session_scope() as session:
        found = {item.id: item for item in instruments_in_universes(session, UNIVERSES)}
        for item in calibration.names:
            instrument = instrument_by_ticker(session, item.ticker)
            if instrument is not None:
                found[instrument.id] = instrument
        names = {
            instrument_id: instrument.ticker
            for instrument_id, instrument in found.items()
            if instrument.asset_class == "equity"
            and instrument.sector not in excluded_sectors
            and instrument.ticker not in excluded_tickers
        }
        ids = list(names)
        closes = closes_for_instrument_ids(session, ids, start=today - timedelta(days=30))
        adj = adj_closes_for_instrument_ids(session, ids, start=start)
        # Plain copies: the ORM rows expire when the session closes.
        ttm = {
            instrument_id: SimpleNamespace(
                as_of=row.as_of,
                shares=row.shares,
                current_liabilities=row.current_liabilities,
                total_liabilities=row.total_liabilities,
                deferred_revenue_current=row.deferred_revenue_current,
            )
            for instrument_id, row in latest_metric_ttm_map(session, ids).items()
        }
        risk_free_points = macro_observations(
            session, RISK_FREE_SERIES, start=today - timedelta(days=30)
        )
        oas_bp = {}
        for bucket, _grade, oas_id, _yield_id in OAS_SERIES:
            points = macro_observations(session, oas_id, start=today - timedelta(days=30))
            if points:
                oas_bp[bucket] = float(points[-1][1]) * 100
    if not risk_free_points:
        raise RuntimeError(f"{RISK_FREE_SERIES} missing: run ingest_fred")
    risk_free = float(risk_free_points[-1][1]) / 100

    inputs: dict[int, CreditInputs] = {}
    fits: dict[str, MertonFit] = {}
    reasons: dict[str, int] = {}
    for instrument_id, ticker in names.items():
        found_inputs, reason = credit_inputs(
            closes.get(instrument_id, []),
            adj.get(instrument_id, []),
            ttm.get(instrument_id),
            today=today,
        )
        if found_inputs is None:
            key = (reason or "unknown").split(" ")[0]
            reasons[key] = reasons.get(key, 0) + 1
            continue
        fit = merton(
            found_inputs.market_cap, found_inputs.point, found_inputs.vol_equity, risk_free
        )
        if fit is None:
            reasons["unsolved"] = reasons.get("unsolved", 0) + 1
            continue
        inputs[instrument_id] = found_inputs
        fits[ticker] = fit

    ladder = fit_ladder(fits, calibration, oas_bp)
    if len(ladder) < 3:
        raise RuntimeError(f"calibration ladder too short ({len(ladder)} buckets)")
    rows: list[dict[str, object]] = []
    for instrument_id, item in inputs.items():
        fit = fits[names[instrument_id]]
        placement = place(fit.dd, ladder)
        if placement is None:
            continue
        rows.append(
            {
                "instrument_id": instrument_id,
                "as_of": item.close_as_of,
                "statement_as_of": item.statement_as_of,
                "market_cap": _dec(item.market_cap, 2),
                "default_point": _dec(item.point, 2),
                "vol_equity": _dec(item.vol_equity, 6),
                "asset_value": _dec(fit.asset_value, 2),
                "vol_asset": _dec(fit.vol_asset, 6),
                "risk_free": _dec(risk_free, 6),
                "dd": _dec(fit.dd, 4),
                "bucket": placement.bucket,
                "position": placement.position,
                "bucket_oas_bp": _dec(placement.oas_bp, 1),
                "calibration_version": calibration.version,
            }
        )
    as_of = max((row["as_of"] for row in rows), default=today)
    with session_scope() as session:
        written = upsert_credit_implied(session, rows)
        replace_credit_anchors(
            session,
            as_of,
            [
                {
                    "bucket": row.bucket,
                    "median_dd": _dec(row.median_dd, 4),
                    "names": row.names,
                    "oas_bp": _dec(row.oas_bp, 1),
                    "calibration_version": calibration.version,
                }
                for row in ladder
            ],
        )
    return {
        "written": written,
        "skipped": reasons,
        "anchors": {row.bucket: round(row.median_dd, 2) for row in ladder},
        "as_of": as_of,
    }



def _dec(value: float | None, digits: int) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, digits)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Equity-implied credit bucket (Merton DD placed on rating anchors)."
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result: dict[str, object] = {"written": 0}
    try:
        result = compute()
    except Exception as exc:
        record_job(JOB_NAME, status="error", rows_written=0, error=str(exc))
        log.exception("%s failed", JOB_NAME)
        sys.exit(1)
    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["written"]),
        extra={
            "skipped": result["skipped"],
            "anchors": result["anchors"],
            "as_of": str(result["as_of"]),
        },
    )
    log.info(
        "%s as_of=%s written=%s anchors=%s skipped=%s",
        JOB_NAME,
        result["as_of"],
        result["written"],
        result["anchors"],
        result["skipped"],
    )


if __name__ == "__main__":
    main()
