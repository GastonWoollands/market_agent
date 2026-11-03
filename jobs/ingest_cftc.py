"""CFTC Traders in Financial Futures (futures only) for the contracts in cftc_contracts.yaml.

Weekly: positions as of Tuesday, published Friday 15:30 ET. Default re-reads the last eight
weeks (CFTC revises); `--backfill` loads three years plus a quarter for the percentile.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from ingest.cftc import CftcClient
from jobs.runtime import tracked_job
from store.catalog import load_cftc
from store.engine import session_scope
from store.repos import upsert_cot_positions

log = logging.getLogger("jobs.ingest_cftc")
JOB_NAME = "ingest_cftc"
DEFAULT_WEEKS = 8
BACKFILL_DAYS = 3 * 365 + 91


def ingest(*, backfill: bool = False, today: date | None = None) -> dict[str, object]:
    today = today or date.today()
    catalog = load_cftc()
    since = today - timedelta(days=BACKFILL_DAYS if backfill else DEFAULT_WEEKS * 7)
    with CftcClient() as client:
        reports = client.tff_reports(catalog.codes(), since=since)
    found = {report.contract_code for report in reports}
    missing = [item.label for item in catalog.contracts if item.code not in found]
    if missing:
        raise RuntimeError(f"CFTC returned no reports for {missing} since {since}")
    with session_scope() as session:
        written = upsert_cot_positions(session, [report.model_dump() for report in reports])
    latest = max(report.report_date for report in reports)
    return {"rows": written, "latest": latest}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest CFTC TFF positioning.")
    parser.add_argument(
        "--backfill", action="store_true", help="Load three years (+ a quarter) of reports."
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        with tracked_job(JOB_NAME) as run:
            result = ingest(backfill=args.backfill)
            run.rows = int(result["rows"])
            run.extra = {"latest": str(result["latest"]), "source": "cftc"}
            log.info("ingest_cftc rows=%s latest=%s", result["rows"], result["latest"])
    except Exception:
        log.exception("ingest_cftc failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
