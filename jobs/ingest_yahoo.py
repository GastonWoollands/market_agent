from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from ingest.yahoo import YahooClient
from ingest.yahoo.errors import YahooError, YahooHttpError
from jobs.runtime import record_job
from store.engine import session_scope
from store.repos import (
    bar_count_for_ticker,
    instruments_in_universe,
    upsert_daily_bars,
    upsert_quotes,
)

log = logging.getLogger("jobs.ingest_yahoo")
JOB_NAME = "ingest_yahoo"
DEFAULT_UNIVERSE = "tape"
CHART_RANGE = "5y"
REQUIRED = {"tape": ("SPY", "XLK")}


@dataclass(frozen=True)
class TapeInstrument:
    id: int
    ticker: str
    yahoo_symbol: str


def ingest(
    *, tickers: set[str] | None = None, universe: str = DEFAULT_UNIVERSE
) -> dict[str, int | list[str]]:
    with session_scope() as session:
        instruments = [
            TapeInstrument(item.id, item.ticker, item.yahoo_symbol)
            for item in instruments_in_universe(session, universe)
        ]
    if tickers:
        wanted = {ticker.upper() for ticker in tickers}
        instruments = [item for item in instruments if item.ticker.upper() in wanted]
    if not instruments:
        raise RuntimeError(f"{universe} universe is empty — run the seed/SEC job first")

    by_yahoo = {item.yahoo_symbol: item for item in instruments}
    failures: list[str] = []
    bar_rows = 0
    quote_rows = 0
    required = {ticker.upper() for ticker in REQUIRED.get(universe, ())}
    if tickers:
        required &= {ticker.upper() for ticker in tickers}
    ordered = sorted(instruments, key=lambda item: item.ticker.upper() not in required)
    rate_limited = False

    with YahooClient() as client:
        for index, instrument in enumerate(ordered, start=1):
            try:
                bars = client.fetch_chart(instrument.yahoo_symbol, range_=CHART_RANGE)
            except YahooHttpError as exc:
                log.warning("%s chart failed: %s", instrument.ticker, exc)
                failures.append(f"{instrument.ticker}: {exc}")
                if exc.status_code == 429:
                    rate_limited = True
                    break
                continue
            except (YahooError, ValueError) as exc:
                log.warning("%s chart failed: %s", instrument.ticker, exc)
                failures.append(f"{instrument.ticker}: {exc}")
                continue
            with session_scope() as session:
                bar_rows += upsert_daily_bars(session, instrument.id, bars)
            if index % 50 == 0:
                log.info("yahoo %s %s/%s", universe, index, len(ordered))

        if not rate_limited and universe == "tape":
            try:
                snapshots = client.fetch_quotes(list(by_yahoo))
                mapped_quotes = [
                    (by_yahoo[snap.yahoo_symbol].id, snap)
                    for snap in snapshots
                    if snap.yahoo_symbol in by_yahoo
                ]
                with session_scope() as session:
                    quote_rows = upsert_quotes(session, mapped_quotes)
            except (YahooError, TypeError, ValueError) as exc:
                log.warning("quote batch failed: %s", exc)
                failures.append(f"quotes: {exc}")

    with session_scope() as session:
        missing_required = [
            ticker for ticker in required if bar_count_for_ticker(session, ticker) == 0
        ]
    if missing_required:
        raise RuntimeError(f"required tickers have no daily bars: {missing_required}")

    return {
        "bar_rows": bar_rows,
        "quote_rows": quote_rows,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Yahoo daily bars and quotes.")
    parser.add_argument(
        "--tickers",
        help="Optional comma-separated tickers (default: full universe).",
    )
    parser.add_argument(
        "--universe",
        default=DEFAULT_UNIVERSE,
        choices=("tape", "valuation"),
        help="Which universe to pull bars for.",
    )
    args = parser.parse_args()
    selected = (
        {part.strip().upper() for part in args.tickers.split(",") if part.strip()}
        if args.tickers
        else None
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"bar_rows": 0, "quote_rows": 0, "failures": []}
    try:
        result = ingest(tickers=selected, universe=args.universe)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("bar_rows") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_yahoo failed")
        raise SystemExit(1) from exc

    failures = result["failures"]
    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["bar_rows"]) + int(result["quote_rows"]),
        extra={
            "bar_rows": result["bar_rows"],
            "quote_rows": result["quote_rows"],
            "failures": failures,
            "universe": args.universe,
            "source": "yahoo",
        },
    )
    log.info(
        "ingest_yahoo bars=%s quotes=%s failures=%s",
        result["bar_rows"],
        result["quote_rows"],
        len(failures) if isinstance(failures, list) else failures,
    )


if __name__ == "__main__":
    sys.exit(main())
