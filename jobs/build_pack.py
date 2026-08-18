from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agent.pack import pack_from_store, pack_hash
from jobs.runtime import record_job
from store.engine import session_scope
from store.repos import upsert_evidence_pack

log = logging.getLogger("jobs.build_pack")
JOB_NAME = "build_pack"
ET = ZoneInfo("America/New_York")


def build(*, as_of: date | None = None) -> dict[str, object]:
    day = as_of or datetime.now(ET).date()
    with session_scope() as session:
        payload = pack_from_store(session, as_of=day)
        digest = pack_hash(payload)
        row = upsert_evidence_pack(session, as_of=day, pack=payload, digest=digest)
        pack_id = row.id
    return {
        "as_of": day.isoformat(),
        "hash": digest,
        "pack_id": pack_id,
        "sources": len(payload["sources"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build today's evidence pack from Postgres.")
    parser.add_argument("--as-of", help="YYYY-MM-DD (default: today America/New_York).")
    args = parser.parse_args()
    chosen = date.fromisoformat(args.as_of) if args.as_of else None
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result: dict[str, object] = {"pack_id": 0}
    try:
        result = build(as_of=chosen)
    except Exception as exc:
        record_job(JOB_NAME, status="error", rows_written=0, error=str(exc))
        log.exception("build_pack failed")
        raise SystemExit(1) from exc

    record_job(JOB_NAME, status="ok", rows_written=1, extra=result)
    log.info(
        "build_pack as_of=%s hash=%s sources=%s",
        result["as_of"],
        result["hash"],
        result["sources"],
    )


if __name__ == "__main__":
    sys.exit(main())
