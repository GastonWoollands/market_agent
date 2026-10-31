"""Sector / industry for SEC-backed names from the submissions endpoint (SIC code)."""

from __future__ import annotations

import argparse
import logging
import sys

from analytics.sectors import load_sic_map
from ingest.sec.client import SecClient
from ingest.sec.errors import SecError, SecHttpError, SecParseError
from jobs.runtime import tracked_job
from store.engine import session_scope
from store.repos import instruments_in_universes, set_instrument_profile
from store.settings import settings

log = logging.getLogger("jobs.ingest_sec_profile")
JOB_NAME = "ingest_sec_profile"
UNIVERSES = ("valuation", "watchlist")


def ingest(*, tickers: set[str] | None = None, resume: bool = False) -> dict[str, object]:
    sic_map = load_sic_map()
    with session_scope() as session:
        rows = [
            (item.id, item.ticker, item.cik, item.sector)
            for item in instruments_in_universes(session, UNIVERSES)
            if item.cik
        ]
    if tickers:
        rows = [item for item in rows if item[1].upper() in tickers]
    if resume:
        rows = [item for item in rows if not item[3]]
    written = 0
    unmapped: list[str] = []
    failures: list[str] = []
    with SecClient(settings.sec_user_agent) as client:
        for index, (instrument_id, ticker, cik, _sector) in enumerate(rows, start=1):
            try:
                profile = client.fetch_profile(cik)
            except SecHttpError as exc:
                if exc.status_code == 429:
                    raise RuntimeError("SEC rate limited") from exc
                failures.append(f"{ticker}: {exc}")
                continue
            except (SecParseError, SecError, ValueError) as exc:
                failures.append(f"{ticker}: {exc}")
                continue
            sector = sic_map.sector_for(profile.sic, ticker)
            if sector is None:
                unmapped.append(f"{ticker}:{profile.sic}")
            with session_scope() as session:
                set_instrument_profile(
                    session, instrument_id, sector=sector, industry=profile.sic_description
                )
            written += 1
            if index % 200 == 0:
                log.info("sec profile %s/%s", index, len(rows))
    if unmapped:
        log.warning("unmapped SIC codes (%s): %s", len(unmapped), ", ".join(unmapped[:20]))
    return {"written": written, "unmapped": unmapped, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write instrument sector / industry from SEC submissions (SIC)."
    )
    parser.add_argument("--tickers", help="Optional comma-separated tickers.")
    parser.add_argument(
        "--resume", action="store_true", help="Skip names that already have a sector."
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    selected = (
        {part.strip().upper() for part in args.tickers.split(",") if part.strip()}
        if args.tickers
        else None
    )
    try:
        with tracked_job(JOB_NAME) as run:
            result = ingest(tickers=selected, resume=args.resume)
            run.rows = int(result["written"])
            run.extra = {
                "unmapped": len(result["unmapped"]),
                "failures": result["failures"][:20],
            }
    except Exception:
        log.exception("%s failed", JOB_NAME)
        sys.exit(1)
    log.info(
        "%s written=%s unmapped=%s failures=%s",
        JOB_NAME,
        result["written"],
        len(result["unmapped"]),
        len(result["failures"]),
    )


if __name__ == "__main__":
    main()
