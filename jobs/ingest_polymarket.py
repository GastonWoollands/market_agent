from __future__ import annotations

import argparse
import logging
import sys

from ingest.polymarket import PolymarketClient
from ingest.polymarket.errors import PolymarketError, PolymarketHttpError
from jobs.runtime import record_job
from store.catalog import load_polymarket
from store.engine import session_scope
from store.repos import latest_odds, upsert_odds

log = logging.getLogger("jobs.ingest_polymarket")
JOB_NAME = "ingest_polymarket"


def _suggestions(client: PolymarketClient, hints: list[str]) -> list[str]:
    found: list[str] = []
    for hint in hints[:2]:
        try:
            for event in client.search_events(hint)[:3]:
                slug = event.get("slug") if isinstance(event, dict) else None
                if isinstance(slug, str) and slug not in found:
                    found.append(slug)
        except PolymarketError as exc:
            log.warning("search %s failed: %s", hint, exc)
    return found


def ingest(*, slugs: set[str] | None = None) -> dict[str, int | list[str]]:
    catalog = load_polymarket()
    items = list(catalog.events)
    if slugs:
        wanted = {item.lower() for item in slugs}
        items = [item for item in items if item.slug.lower() in wanted]
    if not items:
        raise RuntimeError("Polymarket catalog is empty")

    failures: list[str] = []
    written = 0
    with PolymarketClient() as client:
        for item in items:
            try:
                point = client.fetch_event(item.slug)
            except PolymarketHttpError as exc:
                extra = ""
                if exc.status_code == 404:
                    hints = catalog.search_hints.get(item.category, [])
                    found = _suggestions(client, hints)
                    if found:
                        extra = f"; search candidates: {found}"
                log.warning("%s fetch failed: %s%s", item.slug, exc, extra)
                failures.append(f"{item.slug}: {exc}{extra}")
                if exc.status_code == 429:
                    raise RuntimeError("Gamma rate limited") from exc
                continue
            except (PolymarketError, ValueError) as exc:
                log.warning("%s fetch failed: %s", item.slug, exc)
                failures.append(f"{item.slug}: {exc}")
                continue
            with session_scope() as session:
                upsert_odds(session, point)
                written += 1

    with session_scope() as session:
        have = {row.slug for row in latest_odds(session)}
    missing_live = [item.slug for item in items if item.show_on_live and item.slug not in have]
    if missing_live:
        raise RuntimeError(f"required Live odds missing: {missing_live}")

    return {"odds_rows": written, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Polymarket Gamma odds for curated slugs.")
    parser.add_argument(
        "--slugs",
        help="Optional comma-separated event slugs (default: full catalog).",
    )
    args = parser.parse_args()
    selected = None
    if args.slugs:
        selected = {part.strip().lower() for part in args.slugs.split(",") if part.strip()}
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"odds_rows": 0, "failures": []}
    try:
        result = ingest(slugs=selected)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("odds_rows") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_polymarket failed")
        raise SystemExit(1) from exc

    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["odds_rows"]),
        extra={"failures": result["failures"], "source": "polymarket"},
    )
    log.info(
        "ingest_polymarket rows=%s failures=%s",
        result["odds_rows"],
        len(result["failures"]) if isinstance(result["failures"], list) else result["failures"],
    )


if __name__ == "__main__":
    sys.exit(main())
