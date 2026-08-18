from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from ingest.yahoo import YahooClient
from ingest.yahoo.errors import YahooError, YahooHttpError
from jobs.runtime import record_job
from store.engine import session_scope
from store.repos import instruments_in_universes, upsert_intraday_bars

log = logging.getLogger("jobs.ingest_intraday")
JOB_NAME = "ingest_intraday"
DEFAULT_UNIVERSES = ("tape", "watchlist")
INTERVAL = "5m"
CHART_RANGE = "5d"


@dataclass(frozen=True)
class TapeInstrument:
    id: int
    ticker: str
    yahoo_symbol: str


def ingest(*, tickers: set[str] | None = None) -> dict[str, int | list[str]]:
    with session_scope() as session:
        instruments = [
            TapeInstrument(item.id, item.ticker, item.yahoo_symbol)
            for item in instruments_in_universes(session, DEFAULT_UNIVERSES)
        ]
    if tickers:
        wanted = {ticker.upper() for ticker in tickers}
        instruments = [item for item in instruments if item.ticker.upper() in wanted]
    if not instruments:
        raise RuntimeError("tape/watchlist universes are empty — run seed_tape first")

    failures: list[str] = []
    bar_rows = 0
    rate_limited = False

    with YahooClient() as client:
        for index, instrument in enumerate(instruments, start=1):
            try:
                bars = client.fetch_intraday(
                    instrument.yahoo_symbol, range_=CHART_RANGE, interval=INTERVAL
                )
            except YahooHttpError as exc:
                log.warning("%s 5m failed: %s", instrument.ticker, exc)
                failures.append(f"{instrument.ticker}: {exc}")
                if exc.status_code == 429:
                    rate_limited = True
                    break
                continue
            except (YahooError, ValueError) as exc:
                log.warning("%s 5m failed: %s", instrument.ticker, exc)
                failures.append(f"{instrument.ticker}: {exc}")
                continue
            with session_scope() as session:
                bar_rows += upsert_intraday_bars(session, instrument.id, bars)
            if index % 25 == 0:
                log.info("intraday %s/%s", index, len(instruments))

    return {
        "bar_rows": bar_rows,
        "failures": failures,
        "rate_limited": int(rate_limited),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Yahoo 5m extended-hours bars for tape + watchlist only."
    )
    parser.add_argument(
        "--tickers",
        help="Optional comma-separated tickers (default: tape ∪ watchlist).",
    )
    args = parser.parse_args()
    selected = (
        {part.strip().upper() for part in args.tickers.split(",") if part.strip()}
        if args.tickers
        else None
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"bar_rows": 0, "failures": []}
    try:
        result = ingest(tickers=selected)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("bar_rows") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_intraday failed")
        raise SystemExit(1) from exc

    failures = result["failures"]
    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["bar_rows"]),
        extra={
            "bar_rows": result["bar_rows"],
            "failures": failures,
            "interval": INTERVAL,
            "source": "yahoo",
        },
    )
    log.info(
        "ingest_intraday bars=%s failures=%s",
        result["bar_rows"],
        len(failures) if isinstance(failures, list) else failures,
    )


if __name__ == "__main__":
    sys.exit(main())
