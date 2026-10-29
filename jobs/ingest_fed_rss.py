from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta

from ingest.fed_rss import FedRssClient
from ingest.fed_rss.client import FEEDS
from ingest.fed_rss.errors import FedRssError, FedRssHttpError
from ingest.fed_rss.parse import is_venue_excerpt
from jobs.runtime import schema_behind_error, tracked_job
from store.canonical import PolicyDoc
from store.engine import session_scope
from store.repos import policy_excerpts, upsert_policy_items

log = logging.getLogger("jobs.ingest_fed_rss")
JOB_NAME = "ingest_fed_rss"
BODY_LOOKBACK = timedelta(days=14)
BODY_KINDS = frozenset({"statement", "minutes", "speech", "testimony"})


def ingest(*, kinds: set[str] | None = None) -> dict[str, int | list[str]]:
    feeds = list(FEEDS)
    if kinds:
        wanted = {item.lower() for item in kinds}
        feeds = [
            name
            for name in feeds
            if name in wanted
            or (name == "press_monetary" and ("statement" in wanted or "minutes" in wanted))
            or (name == "speeches" and "speech" in wanted)
            or (name == "testimony" and "testimony" in wanted)
        ]
    if not feeds:
        raise RuntimeError("no Fed RSS feeds selected")

    failures: list[str] = []
    written = 0
    with FedRssClient() as client:
        for feed in feeds:
            try:
                docs = client.fetch_feed(feed)
            except FedRssHttpError as exc:
                log.warning("%s failed: %s", feed, exc)
                failures.append(f"{feed}: {exc}")
                if exc.status_code == 429:
                    raise RuntimeError("Fed Board RSS rate limited") from exc
                continue
            except (FedRssError, ValueError) as exc:
                log.warning("%s failed: %s", feed, exc)
                failures.append(f"{feed}: {exc}")
                continue
            docs = _with_bodies(client, docs, failures)
            try:
                with session_scope() as session:
                    written += upsert_policy_items(session, docs)
            except Exception as exc:
                behind = schema_behind_error(exc)
                if behind is not None:
                    raise behind from exc
                raise

    if written == 0:
        raise RuntimeError(f"no policy rows written; failures={failures}")
    return {"policy_rows": written, "failures": failures, "feeds": feeds}


def _with_bodies(
    client: FedRssClient, docs: list[PolicyDoc], failures: list[str]
) -> list[PolicyDoc]:
    """Swap thin RSS descriptions for the article body; keep bodies already stored."""
    with session_scope() as session:
        stored = policy_excerpts(session, [doc.guid for doc in docs])
    cutoff = datetime.now(UTC) - BODY_LOOKBACK
    out: list[PolicyDoc] = []
    for doc in docs:
        kept = stored.get(doc.guid)
        if kept and len(kept) > len(doc.excerpt or ""):
            out.append(doc.model_copy(update={"excerpt": kept}))
            continue
        thin = is_venue_excerpt(doc.excerpt) or (doc.excerpt or "").strip() == doc.title.strip()
        if doc.kind not in BODY_KINDS or doc.published_at < cutoff or not thin:
            out.append(doc)
            continue
        try:
            body = client.fetch_body(doc.url)
        except FedRssHttpError as exc:
            if exc.status_code == 429:
                raise RuntimeError("Fed Board site rate limited") from exc
            log.warning("%s body failed: %s", doc.url, exc)
            failures.append(f"body {doc.url}: {exc}")
            body = None
        except FedRssError as exc:
            log.warning("%s body skipped: %s", doc.url, exc)
            body = None
        out.append(doc.model_copy(update={"excerpt": body}) if body else doc)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Federal Reserve Board RSS feeds.")
    parser.add_argument(
        "--kinds",
        help="Optional comma-separated kinds: speech,statement,minutes,testimony.",
    )
    args = parser.parse_args()
    selected = None
    if args.kinds:
        selected = {part.strip().lower() for part in args.kinds.split(",") if part.strip()}
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    with tracked_job(JOB_NAME) as run:
        result = ingest(kinds=selected)
        run.rows = int(result["policy_rows"])
        run.extra = {
            "failures": result["failures"],
            "feeds": result["feeds"],
            "source": "fed_rss",
        }
    log.info(
        "ingest_fed_rss rows=%s failures=%s",
        result["policy_rows"],
        len(result["failures"]) if isinstance(result["failures"], list) else result["failures"],
    )


if __name__ == "__main__":
    sys.exit(main())
