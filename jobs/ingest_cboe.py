"""Cboe daily market statistics (put/call ratios, volume and OI by product).

The trading calendar is the stored SPY bars: every SPY session without a row is fetched.
Default looks back 10 sessions; `--backfill` goes to the first verified file (2025-03-03).
Cboe publishes around 18:00 ET, so today's file may not exist yet; an older missing
session is an error.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ingest.cboe import CboeClient
from jobs.runtime import tracked_job
from store.engine import session_scope
from store.repos import closes_for_tickers, options_market_dates, upsert_options_market_stats

log = logging.getLogger("jobs.ingest_cboe")
JOB_NAME = "ingest_cboe"
CALENDAR_TICKER = "SPY"
FIRST_FILE = date(2025, 3, 3)
DEFAULT_SESSIONS = 10
ET = ZoneInfo("America/New_York")


def ingest(*, backfill: bool = False, today: date | None = None) -> dict[str, object]:
    today = today or datetime.now(ET).date()
    with session_scope() as session:
        sessions = [
            day
            for day, _close in closes_for_tickers(session, [CALENDAR_TICKER], start=FIRST_FILE)[
                CALENDAR_TICKER
            ]
        ]
        stored = options_market_dates(session)
    if not sessions:
        raise RuntimeError(f"no {CALENDAR_TICKER} bars: run ingest_yahoo first")
    window = sessions if backfill else sessions[-DEFAULT_SESSIONS:]
    wanted = [day for day in window if day not in stored]
    written = 0
    missing: list[date] = []
    with CboeClient() as client:
        for index, day in enumerate(wanted, start=1):
            stats = client.fetch_day(day)
            if stats is None:
                missing.append(day)
                continue
            with session_scope() as session:
                written += upsert_options_market_stats(
                    session, [item.model_dump() for item in stats]
                )
            if index % 50 == 0:
                log.info("cboe %s/%s", index, len(wanted))
    stale = [day for day in missing if day < today]
    if stale and stale[-1] == window[-1]:
        raise RuntimeError(f"Cboe has no file for the latest session {stale[-1]}")
    return {"rows": written, "days": len(wanted) - len(missing), "missing": missing}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Cboe daily put/call statistics.")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=f"Fetch every stored SPY session since {FIRST_FILE} that has no row.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        with tracked_job(JOB_NAME) as run:
            result = ingest(backfill=args.backfill)
            missing = [day.isoformat() for day in result["missing"]]
            run.rows = int(result["rows"])
            run.extra = {"days": result["days"], "missing": missing, "source": "cboe"}
            log.info(
                "ingest_cboe rows=%s days=%s missing=%s", result["rows"], result["days"], missing
            )
    except Exception:
        log.exception("ingest_cboe failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
