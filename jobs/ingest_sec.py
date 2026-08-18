from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

from ingest.sec.client import CompanyFactsArchive, SecClient
from ingest.sec.errors import SecError, SecHttpError, SecParseError
from ingest.sec.parse import fresh_ttm, ttm_from_facts, usable_ttm, yahoo_symbol
from jobs.runtime import record_job
from store.catalog import CatalogInstrument, load_universes
from store.engine import session_scope
from store.repos import (
    replace_membership,
    universe_size,
    upsert_instrument,
    upsert_metric_ttm,
    upsert_universe,
)
from store.settings import settings

log = logging.getLogger("jobs.ingest_sec")
JOB_NAME = "ingest_sec"
# Northstar: ~900 names. Revenue ≥ $1B plus usable EV/EBITDA XBRL, not a slice of a larger set.
BAND = (700, 1000)


def ingest(
    *,
    refresh_zip: bool = False,
    zip_path: str | None = None,
    per_cik: bool = False,
    limit: int | None = None,
    tickers: set[str] | None = None,
) -> dict[str, int | list[str]]:
    catalog = load_universes().valuation
    floor = Decimal(catalog.min_revenue_usd)
    ua = settings.sec_user_agent.strip()
    if not ua:
        raise RuntimeError("SEC_USER_AGENT is missing")

    failures: list[str] = []
    kept = 0
    with SecClient(ua) as client:
        listed = client.fetch_tickers(exchanges=catalog.exchanges)
        listed = _one_ticker_per_cik(listed)
        if tickers:
            wanted = {item.upper() for item in tickers}
            listed = [item for item in listed if item.ticker.upper() in wanted]
        listed.sort(key=lambda item: item.ticker)
        if limit is not None:
            listed = listed[:limit]
        if not listed:
            raise RuntimeError("no SEC tickers after exchange filter")

        archive: CompanyFactsArchive | None = None
        if not per_cik:
            try:
                path = Path(zip_path) if zip_path else client.ensure_facts_zip(refresh=refresh_zip)
                archive = CompanyFactsArchive(path)
            except (SecHttpError, SecError) as exc:
                log.warning("companyfacts.zip unavailable (%s); per-CIK JSON", exc)
                failures.append(f"zip: {exc}")

        try:
            kept = _write_members(client, listed, floor, archive, failures)
        finally:
            if archive is not None:
                archive.close()

    with session_scope() as session:
        members = universe_size(session, "valuation")
    if tickers is None and limit is None and not (BAND[0] <= members <= BAND[1]):
        raise RuntimeError(f"valuation membership {members} is outside {BAND[0]}–{BAND[1]}")
    return {"members": members, "written": kept, "listed": len(listed), "failures": failures}


def _write_members(client, listed, floor: Decimal, archive, failures: list[str]) -> int:
    kept = 0
    with session_scope() as session:
        universe = upsert_universe(session, "valuation", load_universes().valuation.description)
        session.flush()
        ids: list[int] = []
        for index, item in enumerate(listed, start=1):
            try:
                if archive is not None:
                    metric = client.metric_from_archive(
                        archive, item.cik, require_quarters=True
                    )
                else:
                    metric = ttm_from_facts(
                        client.fetch_companyfacts(item.cik), require_quarters=True
                    )
            except (SecHttpError, SecParseError, SecError, ValueError) as exc:
                failures.append(f"{item.ticker}: {exc}")
                if isinstance(exc, SecHttpError) and exc.status_code == 429:
                    raise RuntimeError("SEC rate limited") from exc
                continue
            if (
                metric is None
                or metric.revenue < floor
                or not fresh_ttm(metric)
                or not usable_ttm(metric)
            ):
                continue
            instrument = upsert_instrument(
                session,
                CatalogInstrument(
                    ticker=item.ticker,
                    yahoo=yahoo_symbol(item.ticker),
                    name=item.name,
                    asset_class="equity",
                    exchange=item.exchange,
                    cik=item.cik,
                ),
            )
            session.flush()
            upsert_metric_ttm(session, instrument.id, metric)
            ids.append(instrument.id)
            kept += 1
            if index % 500 == 0:
                log.info("sec facts %s/%s kept=%s", index, len(listed), kept)
        replace_membership(session, universe.id, ids)
    return kept


def _one_ticker_per_cik(rows):
    best = {}
    for item in rows:
        current = best.get(item.cik)
        if current is None or _preferred(item.ticker, current.ticker):
            best[item.cik] = item
    return list(best.values())


def _preferred(new: str, old: str) -> bool:
    new_class = "-" in new or "." in new
    old_class = "-" in old or "." in old
    if new_class != old_class:
        return not new_class
    if len(new) != len(old):
        return len(new) < len(old)
    return new < old


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the valuation universe from SEC tickers + companyfacts TTM revenue."
    )
    parser.add_argument("--refresh-zip", action="store_true")
    parser.add_argument("--zip", dest="zip_path", help="Path to an existing companyfacts.zip")
    parser.add_argument(
        "--per-cik",
        action="store_true",
        help="Use companyfacts JSON instead of the zip.",
    )
    parser.add_argument("--limit", type=int, help="Cap listed tickers (debug).")
    parser.add_argument("--tickers", help="Optional comma-separated tickers.")
    args = parser.parse_args()
    selected = None
    if args.tickers:
        selected = {part.strip().upper() for part in args.tickers.split(",") if part.strip()}
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"members": 0, "written": 0, "failures": []}
    try:
        result = ingest(
            refresh_zip=args.refresh_zip,
            zip_path=args.zip_path,
            per_cik=args.per_cik,
            limit=args.limit,
            tickers=selected,
        )
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("written") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_sec failed")
        raise SystemExit(1) from exc

    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["written"]),
        extra={
            "members": result["members"],
            "listed": result["listed"],
            "failures": result["failures"],
            "source": "sec",
        },
    )
    log.info(
        "ingest_sec members=%s written=%s listed=%s failures=%s",
        result["members"],
        result["written"],
        result["listed"],
        len(result["failures"]) if isinstance(result["failures"], list) else result["failures"],
    )


if __name__ == "__main__":
    sys.exit(main())
