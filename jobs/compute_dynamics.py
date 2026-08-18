from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from analytics.returns import (
    INDEX_WINDOW,
    LOOKBACK_1M,
    LOOKBACK_1W,
    LOOKBACK_1Y,
    LOOKBACK_3M,
    index_to_100,
    period_return,
)
from analytics.rrg import (
    BENCHMARK,
    MIN_BARS,
    TRAIL_WEEKS,
    compute_rrg,
    select_trail,
)
from jobs.runtime import record_job
from store.catalog import load_universes, tape_with_roles
from store.engine import session_scope
from store.repos import (
    bar_count_for_ticker,
    closes_for_tickers,
    instruments_in_universe,
    upsert_return_stats,
    upsert_rrg_points,
)

log = logging.getLogger("jobs.compute_dynamics")
JOB_NAME = "compute_dynamics"
UNIVERSE = "tape"
HISTORY_DAYS = 548
REQUIRED_TICKERS = ("SPY", "XLK")
MIN_MEMBERS = 5


@dataclass(frozen=True)
class TapeRow:
    id: int
    ticker: str


def _floats(rows: list[tuple[date, Decimal]]) -> list[tuple[date, float]]:
    return [(day, float(value)) for day, value in rows]


def _dec(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(value, 6)))


def _indexed_payload(points: list[tuple[date, float]]) -> list[dict[str, str | float]]:
    return [{"date": day.isoformat(), "value": round(value, 4)} for day, value in points]


def compute() -> dict[str, object]:
    catalog = load_universes()
    members = tape_with_roles(catalog, catalog.live.mover_roles)
    tickers = [item.ticker for item in members]
    if BENCHMARK not in tickers:
        wanted = [BENCHMARK, *tickers]
    else:
        wanted = tickers

    start = date.today() - timedelta(days=HISTORY_DAYS)
    with session_scope() as session:
        instruments = {
            item.ticker: TapeRow(item.id, item.ticker)
            for item in instruments_in_universe(session, UNIVERSE)
        }
        missing_seed = [ticker for ticker in REQUIRED_TICKERS if ticker not in instruments]
        if missing_seed:
            raise RuntimeError(
                f"required tickers missing from tape — run seed_tape: {missing_seed}"
            )
        closes = closes_for_tickers(session, wanted, start=start)

    spy_rows = _floats(closes.get(BENCHMARK, []))
    if len(spy_rows) < MIN_BARS:
        raise RuntimeError("SPY has insufficient daily bars — run ingest_yahoo")

    rrg_rows: list[dict[str, object]] = []
    stats_rows: list[dict[str, object]] = []
    skipped: list[str] = []
    computed: list[str] = []
    as_of: date | None = None

    for item in members:
        instrument = instruments.get(item.ticker)
        series = _floats(closes.get(item.ticker, []))
        if instrument is None or len(series) < MIN_BARS:
            skipped.append(item.ticker)
            continue
        observations = compute_rrg(series, spy_rows)
        if not observations:
            skipped.append(item.ticker)
            continue
        trail = select_trail(observations, weeks=TRAIL_WEEKS)
        point_as_of = observations[-1].as_of
        as_of = point_as_of if as_of is None or point_as_of > as_of else as_of
        for point in trail:
            rrg_rows.append(
                {
                    "instrument_id": instrument.id,
                    "as_of": point.as_of,
                    "rs_ratio": _dec(point.rs_ratio),
                    "rs_momentum": _dec(point.rs_momentum),
                    "quadrant": point.quadrant,
                }
            )
        dates = [day for day, _ in series]
        prices = [value for _, value in series]
        stats_rows.append(
            {
                "instrument_id": instrument.id,
                "as_of": observations[-1].as_of,
                "ret_1w": _dec(period_return(prices, LOOKBACK_1W)),
                "ret_1m": _dec(period_return(prices, LOOKBACK_1M)),
                "ret_3m": _dec(period_return(prices, LOOKBACK_3M)),
                "ret_1y": _dec(period_return(prices, LOOKBACK_1Y)),
                "indexed": _indexed_payload(index_to_100(dates, prices, window=INDEX_WINDOW)),
            }
        )
        computed.append(item.ticker)

    if len(computed) < MIN_MEMBERS:
        raise RuntimeError(f"too few RRG members ({computed}); skipped={skipped}")
    if "XLK" not in computed:
        raise RuntimeError("XLK has no RRG point — need overlapping bars with SPY")

    with session_scope() as session:
        rrg_written = upsert_rrg_points(session, rrg_rows)
        stats_written = upsert_return_stats(session, stats_rows)
        missing_required = [
            ticker for ticker in REQUIRED_TICKERS if bar_count_for_ticker(session, ticker) == 0
        ]
    if missing_required:
        raise RuntimeError(f"required tickers have no daily bars: {missing_required}")

    return {
        "as_of": as_of.isoformat() if as_of else None,
        "members": computed,
        "skipped": skipped,
        "rrg_rows": rrg_written,
        "return_rows": stats_written,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute RRG points and return stats from stored bars."
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result: dict[str, object] = {"rrg_rows": 0, "return_rows": 0, "members": [], "skipped": []}
    try:
        result = compute()
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("rrg_rows") or 0),
            error=str(exc),
            extra={k: result.get(k) for k in ("members", "skipped")},
        )
        log.exception("compute_dynamics failed")
        raise SystemExit(1) from exc

    written = int(result["rrg_rows"]) + int(result["return_rows"])
    record_job(JOB_NAME, status="ok", rows_written=written, extra=result)
    log.info(
        "compute_dynamics as_of=%s members=%s rrg=%s returns=%s skipped=%s",
        result["as_of"],
        result["members"],
        result["rrg_rows"],
        result["return_rows"],
        result["skipped"],
    )


if __name__ == "__main__":
    sys.exit(main())
