from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from analytics.session import ET
from ingest.sec.client import CompanyFactsArchive, SecClient
from ingest.sec.errors import SecError, SecHttpError, SecParseError
from ingest.sec.parse import (
    fresh_ttm,
    fy_history_from_facts,
    ttm_from_facts,
    ttm_history_from_facts,
    usable_ttm,
    yahoo_symbol,
)
from ingest.yahoo.client import YahooClient
from jobs.foreign_filers import ForeignFilerReport, ForeignFilerSync
from jobs.runtime import record_job
from store.catalog import CatalogInstrument, load_universes
from store.engine import session_scope
from store.repos import (
    ensure_membership,
    instrument_by_ticker,
    instruments_in_universe,
    instruments_in_universes,
    prune_metric_ttm,
    replace_membership,
    universe_size,
    upsert_instrument,
    upsert_metric_fy,
    upsert_metric_ttm,
    upsert_universe,
)
from store.settings import settings

log = logging.getLogger("jobs.ingest_sec")
FOREIGN_META_KEYS = tuple(ForeignFilerReport().as_meta())
JOB_NAME = "ingest_sec"
# Northstar: ~900 names. Revenue ≥ $1B plus usable EV/EBITDA XBRL, not a slice of a larger set.
BAND = (700, 1000)
# Default run: fresh per-CIK facts for every stored name; membership only changes on --rebuild.
REFRESH_UNIVERSES = ("valuation", "watchlist")
# Commit refresh writes in batches so a late 429 keeps the names already fetched.
REFRESH_BATCH = 50
# Above this share of failed fetches the run does not date the dataset for the strip.
MAX_FETCH_FAILURE_SHARE = 0.05


@dataclass(frozen=True)
class RunPlan:
    """What one ingest_sec invocation does. `full` = no --tickers / --limit."""

    mode: str  # refresh | rebuild | fy_only
    full: bool

    @property
    def enforce_band(self) -> bool:
        """Only a full rebuild replaces membership and must land inside BAND."""
        return self.mode == "rebuild" and self.full

    @property
    def dates_dataset(self) -> bool:
        """Only a full TTM run may stamp facts_as_of for the freshness strip."""
        return self.mode != "fy_only" and self.full


def plan_run(
    *,
    rebuild: bool,
    fy_only: bool,
    members: int,
    tickers: set[str] | None,
    limit: int | None,
    zip_flags: bool,
) -> RunPlan:
    full = tickers is None and limit is None
    if fy_only:
        return RunPlan("fy_only", full)
    if rebuild:
        return RunPlan("rebuild", full)
    if zip_flags:
        raise RuntimeError(
            "--zip / --refresh-zip / --per-cik apply only with --rebuild or --fy-only"
        )
    if members == 0:
        raise RuntimeError(
            "valuation universe is empty — run ingest_sec --rebuild "
            "(add --tickers A,B to load only those names)"
        )
    return RunPlan("refresh", full)


@dataclass
class Tally:
    written: int = 0
    fy_written: int = 0
    listed: int = 0
    fetch_failed: int = 0
    failures: list[str] = field(default_factory=list)
    no_cik: list[str] = field(default_factory=list)

    def fetch_ok_enough(self) -> bool:
        return self.listed > 0 and self.fetch_failed <= MAX_FETCH_FAILURE_SHARE * self.listed


def ingest(
    *,
    rebuild: bool = False,
    refresh_zip: bool = False,
    zip_path: str | None = None,
    per_cik: bool = False,
    limit: int | None = None,
    tickers: set[str] | None = None,
    fy_only: bool = False,
) -> dict[str, int | str | list[str] | None]:
    catalog = load_universes().valuation
    floor = Decimal(catalog.min_revenue_usd)
    ua = settings.sec_user_agent.strip()
    if not ua:
        raise RuntimeError("SEC_USER_AGENT is missing")

    with session_scope() as session:
        stored = universe_size(session, "valuation")
    plan = plan_run(
        rebuild=rebuild,
        fy_only=fy_only,
        members=stored,
        tickers=tickers,
        limit=limit,
        zip_flags=refresh_zip or zip_path is not None or (per_cik and not fy_only and not rebuild),
    )

    tally = Tally()
    foreign: ForeignFilerSync | None = None
    # Date of the SEC data itself: today for per-CIK JSON, the file date for a zip.
    facts_as_of = datetime.now(UTC).astimezone(ET).date()
    with SecClient(ua) as client:
        archive: CompanyFactsArchive | None = None
        if plan.mode != "refresh" and not per_cik:
            try:
                path = Path(zip_path) if zip_path else client.ensure_facts_zip(refresh=refresh_zip)
                archive = CompanyFactsArchive(path)
                facts_as_of = _file_date(path)
            except (SecHttpError, SecError) as exc:
                log.warning("companyfacts.zip unavailable (%s); per-CIK JSON", exc)
                tally.failures.append(f"zip: {exc}")

        try:
            if plan.mode != "fy_only":
                # Curated foreign filers and NULL CIKs first, so this run already refreshes them.
                listed = client.fetch_tickers(exchanges=catalog.exchanges)
                foreign = ForeignFilerSync(catalog, listed)
                curated_ids = foreign.sync_identity(REFRESH_UNIVERSES)
            if plan.mode == "refresh":
                _refresh_stored(client, tally, tickers=tickers, limit=limit)
            elif plan.mode == "fy_only":
                tally.fy_written, tally.listed = _write_fy_only(
                    client, archive, tally.failures, tickers=tickers, limit=limit
                )
            else:
                rows = _one_ticker_per_cik(listed)
                if tickers:
                    wanted = {item.upper() for item in tickers}
                    rows = [item for item in rows if item.ticker.upper() in wanted]
                    found = {item.ticker.upper() for item in rows}
                    tally.failures.extend(
                        f"{name}: not in SEC ticker list" for name in sorted(wanted - found)
                    )
                rows.sort(key=lambda item: item.ticker)
                if limit is not None:
                    rows = rows[:limit]
                if not rows:
                    raise RuntimeError("no SEC tickers after exchange filter")
                tally.listed = len(rows)
                _write_members(
                    client,
                    rows,
                    floor,
                    archive,
                    tally,
                    enforce_band=plan.enforce_band,
                    keep_ids=curated_ids,
                )
        finally:
            if archive is not None:
                archive.close()

    if foreign is not None:
        # Vendor quarters only after the SEC pass, so they never shadow a newer filing.
        with YahooClient() as yahoo:
            foreign.write_yahoo_ttm(yahoo, foreign.selected(tickers))
        tally.failures.extend(foreign.report.failures)

    with session_scope() as session:
        members = universe_size(session, "valuation")
    if plan.enforce_band and not (BAND[0] <= members <= BAND[1]):
        raise RuntimeError(f"valuation membership {members} is outside {BAND[0]}–{BAND[1]}")
    dated = plan.dates_dataset and tally.fetch_ok_enough()
    if plan.dates_dataset and not dated:
        log.warning(
            "%s of %s fetches failed; facts_as_of not recorded", tally.fetch_failed, tally.listed
        )
    return {
        "members": members,
        "written": tally.written,
        "fy_written": tally.fy_written,
        "listed": tally.listed,
        "failures": tally.failures,
        "no_cik": tally.no_cik,
        "mode": plan.mode,
        "facts_as_of": facts_as_of.isoformat() if dated else None,
        **(foreign.report.as_meta() if foreign is not None else {}),
    }


def _refresh_stored(client, tally: Tally, *, tickers: set[str] | None, limit: int | None) -> None:
    """Fresh facts for stored names by their stored CIK. Never touches membership."""
    with session_scope() as session:
        stored = instruments_in_universes(session, REFRESH_UNIVERSES)
        names = [(item.id, item.ticker, item.cik) for item in stored]
    if tickers:
        wanted = {item.upper() for item in tickers}
        found = {ticker.upper() for _id, ticker, _cik in names}
        tally.failures.extend(
            f"{name}: not stored — use --rebuild --tickers {name}"
            for name in sorted(wanted - found)
        )
        names = [item for item in names if item[1].upper() in wanted]
    # ETFs and foreign filers have no CIK: reported apart so real failures stand out.
    tally.no_cik = sorted(ticker for _id, ticker, cik in names if not cik)
    names = [item for item in names if item[2]]
    if limit is not None:
        names = names[:limit]
    tally.listed = len(names)
    for start in range(0, len(names), REFRESH_BATCH):
        with session_scope() as session:
            for instrument_id, ticker, cik in names[start : start + REFRESH_BATCH]:
                payload = _fetch(client, None, cik, ticker, tally)
                if not payload:
                    continue
                try:
                    metric = ttm_from_facts(payload, require_quarters=True)
                except (SecParseError, ValueError) as exc:
                    tally.failures.append(f"{ticker}: {exc}")
                    continue
                tally.fy_written += _write_facts(session, instrument_id, payload, metric)
                tally.written += 1
        log.info(
            "sec refresh %s/%s written=%s",
            min(start + REFRESH_BATCH, len(names)),
            len(names),
            tally.written,
        )


def _fetch(client, archive, cik: str, ticker: str, tally: Tally) -> dict | None:
    try:
        if archive is not None:
            return archive.load(cik)
        return client.fetch_companyfacts(cik)
    except (SecHttpError, SecParseError, SecError, ValueError) as exc:
        tally.failures.append(f"{ticker}: {exc}")
        tally.fetch_failed += 1
        if isinstance(exc, SecHttpError) and exc.status_code == 429:
            raise RuntimeError("SEC rate limited") from exc
        return None


def _file_date(path: Path) -> date:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).astimezone(ET).date()


def _write_members(
    client,
    listed,
    floor: Decimal,
    archive,
    tally: Tally,
    *,
    enforce_band: bool,
    keep_ids: list[int] | None = None,
) -> None:
    """Screen SEC listings into valuation; one transaction so a bad rebuild rolls back.

    `keep_ids` (curated foreign filers) stay members whatever the screen says.
    """
    with session_scope() as session:
        universe = upsert_universe(session, "valuation", load_universes().valuation.description)
        session.flush()
        ids: list[int] = []
        for index, item in enumerate(listed, start=1):
            payload = _fetch(client, archive, item.cik, item.ticker, tally)
            if not payload:
                continue
            try:
                metric = ttm_from_facts(payload, require_quarters=True)
            except (SecParseError, ValueError) as exc:
                tally.failures.append(f"{item.ticker}: {exc}")
                continue
            member = (
                metric is not None
                and metric.revenue >= floor
                and fresh_ttm(metric)
                and usable_ttm(metric)
            )
            if not member:
                # A stored name outside the universe (watchlist, a former member) still gets
                # current facts, so the Ticker page never shows rows from an older parse.
                known = instrument_by_ticker(session, item.ticker)
                if known is not None:
                    tally.fy_written += _write_facts(session, known.id, payload, metric)
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
            tally.fy_written += _write_facts(session, instrument.id, payload, metric)
            ids.append(instrument.id)
            tally.written += 1
            if index % 500 == 0:
                log.info("sec facts %s/%s kept=%s", index, len(listed), tally.written)
        if not enforce_band:
            # --rebuild --tickers / --limit adds those names; it must not shrink the universe.
            for instrument_id in ids:
                ensure_membership(session, universe.id, instrument_id)
            return
        ids = sorted({*ids, *(keep_ids or [])})
        # Raise inside the transaction so a bad parse rolls back TTM rows and membership.
        if not (BAND[0] <= len(ids) <= BAND[1]):
            raise RuntimeError(f"valuation membership {len(ids)} is outside {BAND[0]}–{BAND[1]}")
        replace_membership(session, universe.id, ids)


def _write_facts(session, instrument_id: int, payload: dict, metric) -> int:
    """Replace one name's TTM history and upsert its FY rows. Returns FY rows written."""
    snapshots = ttm_history_from_facts(payload, require_quarters=True)
    if metric is not None and metric.as_of not in {snap.as_of for snap in snapshots}:
        snapshots = [*snapshots, metric]
    for snap in snapshots:
        upsert_metric_ttm(session, instrument_id, snap)
    prune_metric_ttm(session, instrument_id, {snap.as_of for snap in snapshots})
    written = 0
    for fy_snap in fy_history_from_facts(payload):
        upsert_metric_fy(session, instrument_id, fy_snap)
        written += 1
    return written


def _write_fy_only(
    client,
    archive,
    failures: list[str],
    *,
    tickers: set[str] | None,
    limit: int | None,
) -> tuple[int, int]:
    with session_scope() as session:
        raw = instruments_in_universe(session, "valuation")
        members = [(item.id, item.ticker, item.cik) for item in raw]
    if tickers:
        wanted = {item.upper() for item in tickers}
        members = [item for item in members if item[1].upper() in wanted]
    if limit is not None:
        members = members[:limit]
    if not members:
        raise RuntimeError("valuation universe is empty — run ingest_sec first")

    fy_written = 0
    with session_scope() as session:
        for index, (instrument_id, ticker, cik) in enumerate(members, start=1):
            if not cik:
                failures.append(f"{ticker}: missing cik")
                continue
            try:
                if archive is not None:
                    payload = archive.load(cik)
                else:
                    payload = client.fetch_companyfacts(cik)
            except (SecHttpError, SecParseError, SecError, ValueError) as exc:
                failures.append(f"{ticker}: {exc}")
                if isinstance(exc, SecHttpError) and exc.status_code == 429:
                    raise RuntimeError("SEC rate limited") from exc
                continue
            if not payload:
                continue
            try:
                snapshots = fy_history_from_facts(payload)
            except (SecParseError, ValueError) as exc:
                failures.append(f"{ticker}: {exc}")
                continue
            for snap in snapshots:
                upsert_metric_fy(session, instrument_id, snap)
                fy_written += 1
            if index % 200 == 0:
                log.info("sec fy-only %s/%s fy_rows=%s", index, len(members), fy_written)
    return fy_written, len(members)


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
        description=(
            "Refresh SEC TTM and FY facts per CIK for stored names (default), "
            "or rebuild the valuation universe from companyfacts.zip (--rebuild)."
        )
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Screen every SEC listing and replace valuation membership (zip unless --per-cik).",
    )
    parser.add_argument("--refresh-zip", action="store_true")
    parser.add_argument("--zip", dest="zip_path", help="Path to an existing companyfacts.zip")
    parser.add_argument(
        "--per-cik",
        action="store_true",
        help="With --rebuild / --fy-only: per-CIK JSON instead of the zip (refresh always is).",
    )
    parser.add_argument("--limit", type=int, help="Cap listed tickers (debug).")
    parser.add_argument(
        "--tickers",
        help="Comma-separated tickers: refresh these stored names (with --rebuild: add them).",
    )
    parser.add_argument(
        "--fy-only",
        action="store_true",
        help="Write metric_fy for current valuation members; do not rebuild membership.",
    )
    args = parser.parse_args()
    selected = None
    if args.tickers:
        selected = {part.strip().upper() for part in args.tickers.split(",") if part.strip()}
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | str | list[str] | None] = {
        "members": 0,
        "written": 0,
        "fy_written": 0,
        "failures": [],
    }
    try:
        result = ingest(
            rebuild=args.rebuild,
            refresh_zip=args.refresh_zip,
            zip_path=args.zip_path,
            per_cik=args.per_cik,
            limit=args.limit,
            tickers=selected,
            fy_only=args.fy_only,
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
            "fy_written": result["fy_written"],
            "failures": result["failures"],
            "no_cik": result["no_cik"],
            "source": "sec",
            "mode": result["mode"],
            **({"facts_as_of": result["facts_as_of"]} if result["facts_as_of"] else {}),
            **{key: result[key] for key in FOREIGN_META_KEYS if key in result},
        },
    )
    log.info(
        "ingest_sec mode=%s facts_as_of=%s members=%s written=%s fy=%s listed=%s failures=%s",
        result["mode"],
        result["facts_as_of"],
        result["members"],
        result["written"],
        result["fy_written"],
        result["listed"],
        len(result["failures"]) if isinstance(result["failures"], list) else result["failures"],
    )


if __name__ == "__main__":
    sys.exit(main())
