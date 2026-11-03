"""Yahoo street EPS revisions (earningsTrend) for the watchlist and the Opportunities top 25.

Two Yahoo calls per name at ≤2 req/s. Names without estimates (ETFs, thin coverage) are
skipped, not errors. Labeled street consensus in the UI; no price targets are stored.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from ingest.yahoo import YahooClient
from ingest.yahoo.errors import YahooError, YahooHttpError
from jobs.runtime import tracked_job
from store.engine import session_scope
from store.repos import (
    instruments_in_universe,
    top_opportunity_instrument_ids,
    upsert_eps_revisions,
)

log = logging.getLogger("jobs.ingest_estimates")
JOB_NAME = "ingest_estimates"
TOP_OPPORTUNITIES = 25
ET = ZoneInfo("America/New_York")


def scope(session) -> list[tuple[int, str, str]]:
    """(instrument id, ticker, Yahoo symbol) for the watchlist ∪ Opportunities top 25."""
    top = set(top_opportunity_instrument_ids(session, TOP_OPPORTUNITIES))
    found = {item.id: item for item in instruments_in_universe(session, "watchlist")}
    for item in instruments_in_universe(session, "valuation"):
        if item.id in top:
            found[item.id] = item
    return [(item.id, item.ticker, item.yahoo_symbol) for item in found.values()]


def ingest() -> dict[str, object]:
    as_of = datetime.now(ET).date()
    with session_scope() as session:
        names = scope(session)
    written = 0
    empty: list[str] = []
    failures: list[str] = []
    with YahooClient(rate=2.0) as client:
        for instrument_id, ticker, symbol in names:
            try:
                revisions = client.fetch_eps_revisions(symbol)
            except YahooHttpError as exc:
                if exc.status_code == 429:
                    raise
                failures.append(f"{ticker}: {exc}")
                continue
            except YahooError as exc:
                failures.append(f"{ticker}: {exc}")
                continue
            if not revisions:
                empty.append(ticker)
                continue
            rows = [
                {
                    "instrument_id": instrument_id,
                    "as_of": as_of,
                    **item.model_dump(exclude={"symbol"}),
                }
                for item in revisions
            ]
            with session_scope() as session:
                written += upsert_eps_revisions(session, rows)
    return {"rows": written, "names": len(names), "empty": empty, "failures": failures}


def main() -> None:
    argparse.ArgumentParser(description="Ingest Yahoo street EPS revisions.").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        with tracked_job(JOB_NAME) as run:
            result = ingest()
            run.rows = int(result["rows"])
            run.extra = {k: result[k] for k in ("names", "empty", "failures")}
            log.info(
                "ingest_estimates rows=%s names=%s empty=%s failures=%s",
                result["rows"],
                result["names"],
                result["empty"],
                result["failures"],
            )
    except Exception:
        log.exception("ingest_estimates failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
