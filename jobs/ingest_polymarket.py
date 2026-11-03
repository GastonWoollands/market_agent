from __future__ import annotations

import argparse
import logging
import sys

from ingest.polymarket import PolymarketClient, load_slot
from ingest.polymarket.errors import PolymarketError, PolymarketHttpError
from ingest.polymarket.resolve import drop_occupied, pending_odds_slug, plan_odds_upserts
from jobs.runtime import record_job
from store.canonical import OddsPoint
from store.catalog import load_polymarket
from store.engine import session_scope
from store.repos import latest_odds, upsert_odds

log = logging.getLogger("jobs.ingest_polymarket")
JOB_NAME = "ingest_polymarket"


def ingest(
    *,
    slugs: set[str] | None = None,
    slots: set[str] | None = None,
) -> dict[str, int | list[str]]:
    catalog = load_polymarket()
    items = list(catalog.events)
    if slots:
        wanted = {item.lower() for item in slots}
        items = [item for item in items if item.slot.lower() in wanted]
    if slugs:
        wanted = {item.lower() for item in slugs}
        items = [
            item
            for item in items
            if item.slug is not None and item.slug.lower() in wanted
        ]
    if not items:
        raise RuntimeError("Polymarket catalog is empty")

    with session_scope() as session:
        current_by_slot = {row.slot: row.slug for row in latest_odds(session)}

    failures: list[str] = []
    points: list[OddsPoint] = []
    with PolymarketClient() as client:
        for item in items:
            previous = current_by_slot.get(item.slot) or item.slug
            try:
                point = load_slot(
                    client,
                    item,
                    current_slug=current_by_slot.get(item.slot),
                    search_hints=catalog.search_hints,
                )
            except PolymarketHttpError as exc:
                log.warning("%s fetch failed: %s", item.slot, exc)
                failures.append(f"{item.slot}: {exc}")
                if exc.status_code == 429:
                    raise RuntimeError("Gamma rate limited") from exc
                continue
            except (PolymarketError, ValueError) as exc:
                log.warning("%s fetch failed: %s", item.slot, exc)
                failures.append(f"{item.slot}: {exc}")
                continue
            if previous and previous != point.slug:
                log.info("%s rotated %s -> %s", item.slot, previous, point.slug)
            points.append(point)

    points, occupied = drop_occupied(points, current_by_slot)
    for message in occupied:
        log.warning("%s", message)
    failures.extend(occupied)
    if points:
        _commit_odds(points, current_by_slot)
    resolved_slots = {point.slot for point in points}
    missing_live = [
        item.slot for item in items if item.show_on_live and item.slot not in resolved_slots
    ]
    if missing_live:
        raise RuntimeError(f"required Live odds missing: {missing_live}")
    return {"odds_rows": len(points), "failures": failures}


def _commit_odds(points: list[OddsPoint], current_by_slot: dict[str, str]) -> None:
    ordered, park_first = plan_odds_upserts(points, current_by_slot)
    with session_scope() as session:
        if park_first:
            for point in ordered:
                current = current_by_slot.get(point.slot)
                if current and current != point.slug:
                    parked = point.model_copy(update={"slug": pending_odds_slug(point.slot)})
                    upsert_odds(session, parked)
        for point in ordered:
            upsert_odds(session, point)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Polymarket Gamma odds for curated slots."
    )
    parser.add_argument(
        "--slots",
        help="Optional comma-separated catalog slots (default: full catalog).",
    )
    parser.add_argument(
        "--slugs",
        help="Optional comma-separated seed slugs (filters catalog rows).",
    )
    args = parser.parse_args()
    selected_slots = None
    selected_slugs = None
    if args.slots:
        selected_slots = {part.strip().lower() for part in args.slots.split(",") if part.strip()}
    if args.slugs:
        selected_slugs = {part.strip().lower() for part in args.slugs.split(",") if part.strip()}
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"odds_rows": 0, "failures": []}
    try:
        result = ingest(slugs=selected_slugs, slots=selected_slots)
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
