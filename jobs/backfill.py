"""Gap-fill using existing ingest jobs. No new vendors."""

from __future__ import annotations

import argparse
import logging
import sys

from jobs import ingest_fred, ingest_intraday, ingest_yahoo
from jobs.runtime import tracked_job

log = logging.getLogger("jobs.backfill")
JOB_NAME = "backfill"


def _csv(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {part.strip().upper() for part in value.split(",") if part.strip()}


def run(
    *,
    source: str,
    universe: str,
    tickers: set[str] | None,
    series: set[str] | None,
    resume: bool,
) -> dict[str, int | list[str]]:
    if source == "yahoo":
        return ingest_yahoo.ingest(tickers=tickers, universe=universe, resume=resume)
    if source == "intraday":
        return ingest_intraday.ingest(tickers=tickers, resume=resume)
    if source == "fred":
        return ingest_fred.ingest(series_ids=series or tickers)
    raise ValueError(f"unknown source: {source}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill stored history via existing Yahoo/FRED jobs. Safe to re-run."
    )
    parser.add_argument("source", choices=("yahoo", "intraday", "fred"))
    parser.add_argument(
        "--universe",
        default="tape",
        choices=("tape", "valuation", "watchlist"),
        help="Yahoo daily universe (ignored for intraday/fred).",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers (yahoo/intraday).")
    parser.add_argument("--series", help="Comma-separated FRED series ids.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Yahoo/intraday: skip names that already have bars.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {}
    try:
        with tracked_job(JOB_NAME) as job:
            result = run(
                source=args.source,
                universe=args.universe,
                tickers=_csv(args.tickers),
                series=_csv(args.series),
                resume=args.resume,
            )
            job.rows = int(
                result.get("bar_rows")
                or result.get("quote_rows")
                or result.get("observation_rows")
                or 0
            )
            job.extra = {
                "source": args.source,
                "universe": args.universe,
                "resume": args.resume,
                "result": result,
            }
            log.info("backfill %s %s", args.source, result)
    except Exception:
        log.exception("backfill failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
