from __future__ import annotations

import logging
import sys

from jobs.runtime import record_job
from store.catalog import load_universes
from store.engine import session_scope
from store.repos import ensure_membership, upsert_instrument, upsert_universe

log = logging.getLogger("jobs.seed_tape")
JOB_NAME = "seed_tape"


def seed() -> int:
    catalog = load_universes()
    rows = 0
    with session_scope() as session:
        for name, bucket in (
            ("tape", catalog.tape),
            ("watchlist", catalog.watchlist),
        ):
            universe = upsert_universe(session, name, bucket.description)
            session.flush()
            for item in bucket.instruments:
                instrument = upsert_instrument(session, item)
                session.flush()
                ensure_membership(session, universe.id, instrument.id)
                rows += 1
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = 0
    try:
        rows = seed()
    except Exception as exc:
        record_job(JOB_NAME, status="error", rows_written=rows, error=str(exc))
        log.exception("seed_tape failed")
        raise SystemExit(1) from exc
    record_job(
        JOB_NAME,
        status="ok",
        rows_written=rows,
        extra={"source": "config/universes.yaml"},
    )
    log.info("seed_tape wrote %s membership rows", rows)


if __name__ == "__main__":
    sys.exit(main())
