"""Per-name price risk (vol, downside vol, beta vs SPY / QQQ, drawdown) from stored bars."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal

from analytics.risk import snapshot
from jobs.runtime import record_job
from store.engine import session_scope
from store.repos import (
    adj_closes_for_instrument_ids,
    instruments_in_universes,
    upsert_risk_stats,
)

log = logging.getLogger("jobs.compute_risk")
JOB_NAME = "compute_risk"
UNIVERSES = ("valuation", "watchlist", "tape")
BENCHMARKS = ("SPY", "QQQ")
LOOKBACK_DAYS = 400


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, 6)))


def compute(*, today: date | None = None) -> dict[str, object]:
    start = (today or date.today()) - timedelta(days=LOOKBACK_DAYS)
    with session_scope() as session:
        members = [
            (item.id, item.ticker)
            for item in instruments_in_universes(session, UNIVERSES)
            if item.asset_class in ("equity", "etf")
        ]
        closes = adj_closes_for_instrument_ids(
            session, [instrument_id for instrument_id, _ticker in members], start=start
        )
    by_ticker = {ticker: instrument_id for instrument_id, ticker in members}
    missing = [item for item in BENCHMARKS if not closes.get(by_ticker.get(item, -1))]
    if missing:
        raise RuntimeError(f"benchmark bars missing: {missing}")
    spy = [(day, float(value)) for day, value in closes[by_ticker["SPY"]]]
    qqq = [(day, float(value)) for day, value in closes[by_ticker["QQQ"]]]
    rows: list[dict[str, object]] = []
    skipped = 0
    for instrument_id, _ticker in members:
        series = [(day, float(value)) for day, value in closes.get(instrument_id, [])]
        risk = snapshot(series, spy=spy, qqq=qqq)
        if risk is None:
            skipped += 1
            continue
        rows.append(
            {
                "instrument_id": instrument_id,
                "as_of": risk.as_of,
                "sessions": risk.sessions,
                "vol_3m": _dec(risk.vol_3m),
                "vol_1y": _dec(risk.vol_1y),
                "downside_vol_1y": _dec(risk.downside_vol_1y),
                "beta_spy": _dec(risk.beta_spy),
                "beta_qqq": _dec(risk.beta_qqq),
                "corr_spy": _dec(risk.corr_spy),
                "max_drawdown_1y": _dec(risk.max_drawdown_1y),
                "drawdown": _dec(risk.drawdown),
            }
        )
    with session_scope() as session:
        written = upsert_risk_stats(session, rows)
    return {
        "written": written,
        "skipped": skipped,
        "as_of": max((row["as_of"] for row in rows), default=None),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vol, downside vol, beta vs SPY/QQQ and drawdown from stored daily bars."
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
        extra={"skipped": result["skipped"], "as_of": str(result["as_of"])},
    )
    log.info(
        "%s as_of=%s written=%s skipped=%s",
        JOB_NAME,
        result["as_of"],
        result["written"],
        result["skipped"],
    )


if __name__ == "__main__":
    main()
