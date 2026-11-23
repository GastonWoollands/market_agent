from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from analytics.splits import ShareBasis
from analytics.valuation import LOOKBACK_DAYS, Fundamental, snapshot
from jobs.runtime import record_job
from store.catalog import load_universes
from store.engine import session_scope
from store.repos import (
    closes_for_instrument_ids,
    delete_valuation_daily,
    instruments_in_universe,
    metric_ttm_history,
    splits_for_instrument_ids,
    upsert_valuation_daily,
)

log = logging.getLogger("jobs.compute_valuation")
JOB_NAME = "compute_valuation"
UNIVERSE = "valuation"


@dataclass(frozen=True)
class Member:
    id: int
    ticker: str


def _dec(value: float | None, places: int = 6) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(value, places)))


def fundamentals(metrics: list, basis: ShareBasis) -> list[Fundamental]:
    """TTM rows usable for EV/EBITDA, shares put on the split basis of the stored closes.

    The basis is placed on the full share series: dropping a negative-EBITDA quarter first
    would break the adjacent-pair match in ShareBasis.
    """
    counted = [metric for metric in metrics if metric.shares is not None and metric.shares > 0]
    factors = basis.factors([(metric.as_of, float(metric.shares)) for metric in counted])
    factor_by_day = {metric.as_of: factor for metric, factor in zip(counted, factors, strict=True)}
    return [
        Fundamental(
            as_of=metric.as_of,
            ebitda=float(metric.ebitda),
            net_debt=float(metric.net_debt),
            shares=float(metric.shares) * factor_by_day[metric.as_of],
        )
        for metric in counted
        if metric.ebitda is not None and metric.net_debt is not None and metric.ebitda > 0
    ]


def compute() -> dict[str, object]:
    start = date.today() - timedelta(days=LOOKBACK_DAYS)
    # Banks (curated, Phase 1.15) get P/E, P/B, ROE; EV/EBITDA does not apply to them.
    banks = load_universes().valuation.bank_tickers
    with session_scope() as session:
        instruments = [
            Member(item.id, item.ticker)
            for item in instruments_in_universe(session, UNIVERSE)
            if item.ticker.upper() not in banks
        ]
        ids = [item.id for item in instruments]
        closes = closes_for_instrument_ids(session, ids, start=start)
        history = metric_ttm_history(session, ids)
        splits = splits_for_instrument_ids(session, ids)
        funds_by_id = {
            instrument_id: fundamentals(metrics, ShareBasis(splits.get(instrument_id, [])))
            for instrument_id, metrics in history.items()
        }
        prices_by_id = {
            instrument_id: [(day, float(close)) for day, close in rows]
            for instrument_id, rows in closes.items()
        }

    if not instruments:
        raise RuntimeError("valuation universe is empty — run ingest_sec first")

    rows: list[dict[str, object]] = []
    skipped: list[str] = []
    skipped_ids: list[int] = []
    comparable = 0
    for instrument in instruments:
        point = snapshot(prices_by_id.get(instrument.id, []), funds_by_id.get(instrument.id, []))
        if point is None:
            skipped.append(instrument.ticker)
            skipped_ids.append(instrument.id)
            continue
        if point.comparable:
            comparable += 1
        rows.append(
            {
                "instrument_id": instrument.id,
                "as_of": point.as_of,
                "ev": _dec(point.ev, 2),
                "ebitda": _dec(point.ebitda, 2),
                "ev_ebitda": _dec(point.ev_ebitda),
                "pctile_5y": _dec(point.pctile_5y, 4),
                "ebitda_growth_1y": _dec(point.ebitda_growth_1y),
                "multiple_change_1y": _dec(point.multiple_change_1y),
                "comparable": point.comparable,
                "sample_size": point.sample_size,
            }
        )

    if not rows:
        raise RuntimeError("no EV/EBITDA rows — need daily bars and metric_ttm")

    with session_scope() as session:
        written = upsert_valuation_daily(session, rows)
        # A member with no snapshot now (e.g. no usable share count) shows no multiple rather
        # than its last one, which scores and the Ticker page would keep reading as current.
        cleared = delete_valuation_daily(session, skipped_ids)

    as_of = max(row["as_of"] for row in rows)
    return {
        "as_of": as_of.isoformat() if isinstance(as_of, date) else str(as_of),
        "written": written,
        "comparable": comparable,
        "members": len(instruments),
        "skipped": skipped,
        "cleared": cleared,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute EV/EBITDA, 5y percentile, and 1y growth × re-rating from stored data."
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result: dict[str, object] = {"written": 0, "comparable": 0, "skipped": []}
    try:
        result = compute()
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("written") or 0),
            error=str(exc),
            extra={"skipped": result.get("skipped", [])},
        )
        log.exception("compute_valuation failed")
        raise SystemExit(1) from exc

    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["written"]),
        extra=result,
    )
    log.info(
        "compute_valuation as_of=%s written=%s comparable=%s/%s skipped=%s cleared=%s",
        result["as_of"],
        result["written"],
        result["comparable"],
        result["members"],
        len(result["skipped"]) if isinstance(result["skipped"], list) else result["skipped"],
        result["cleared"],
    )


if __name__ == "__main__":
    sys.exit(main())
