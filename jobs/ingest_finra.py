"""FINRA consolidated short interest for every stored instrument.

FINRA settles twice a month and publishes about eight business days later. Each run reads
the settlement calendar, then fetches every date not yet stored (the latest date is always
re-read: FINRA revises). One date is ~22k symbols in five pages; rows are kept only for
names we store. Default looks back 60 days; `--backfill` one year.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from ingest.finra import FinraClient, finra_symbol
from jobs.runtime import tracked_job
from store.canonical import ShortInterestReport
from store.engine import session_scope
from store.repos import active_instruments, short_interest_dates, upsert_short_interest

log = logging.getLogger("jobs.ingest_finra")
JOB_NAME = "ingest_finra"
DEFAULT_DAYS = 60
BACKFILL_DAYS = 365


class ShortInterestIngest:
    """Maps FINRA symbols onto stored instruments and writes one settlement date at a time."""

    def __init__(self, client: FinraClient, instrument_ids: dict[str, int]) -> None:
        self._client = client
        self._ids = instrument_ids

    def wanted_dates(self, *, since: date, until: date, stored: set[date]) -> list[date]:
        dates = self._client.settlement_dates(since=since, until=until)
        if not dates:
            raise RuntimeError(f"FINRA lists no settlement dates since {since}")
        return [day for day in dates if day not in stored or day == dates[-1]]

    def rows_for(self, settlement: date) -> list[dict[str, object]]:
        reports = self._client.short_interest(settlement)
        if not reports:
            raise RuntimeError(f"FINRA returned no rows for {settlement}")
        return [self._row(report) for report in reports if report.symbol in self._ids]

    def _row(self, report: ShortInterestReport) -> dict[str, object]:
        fields = report.model_dump(exclude={"symbol"})
        return {"instrument_id": self._ids[report.symbol], **fields}


def ingest(*, backfill: bool = False, today: date | None = None) -> dict[str, object]:
    today = today or date.today()
    since = today - timedelta(days=BACKFILL_DAYS if backfill else DEFAULT_DAYS)
    with session_scope() as session:
        names = active_instruments(session)
        ids = {finra_symbol(item.ticker): item.id for item in names}
        stored = short_interest_dates(session)
    written = 0
    matched: dict[str, int] = {}
    with FinraClient() as client:
        job = ShortInterestIngest(client, ids)
        dates = job.wanted_dates(since=since, until=today, stored=stored)
        for settlement in dates:
            rows = job.rows_for(settlement)
            with session_scope() as session:
                written += upsert_short_interest(session, rows)
            matched[settlement.isoformat()] = len(rows)
            log.info("finra %s: %s of %s names", settlement, len(rows), len(ids))
    return {"rows": written, "dates": matched}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FINRA short interest.")
    parser.add_argument("--backfill", action="store_true", help="Load one year of cycles.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        with tracked_job(JOB_NAME) as run:
            result = ingest(backfill=args.backfill)
            run.rows = int(result["rows"])
            run.extra = {"dates": result["dates"], "source": "finra"}
            log.info("ingest_finra rows=%s dates=%s", result["rows"], list(result["dates"]))
    except Exception:
        log.exception("ingest_finra failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
