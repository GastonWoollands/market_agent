from __future__ import annotations

import argparse
import logging
import sys

from ingest.news_rss import NewsClient
from ingest.news_rss.errors import NewsError, NewsHttpError
from jobs.runtime import record_job
from store.catalog import load_news_queries
from store.engine import session_scope
from store.repos import upsert_news

log = logging.getLogger("jobs.ingest_news")
JOB_NAME = "ingest_news"


def ingest(*, categories: set[str] | None = None) -> dict[str, int | list[str]]:
    catalog = load_news_queries()
    buckets = list(catalog.buckets)
    if categories:
        wanted = {item.lower() for item in categories}
        buckets = [item for item in buckets if item.category.lower() in wanted]
    if not buckets:
        raise RuntimeError("news query catalog is empty")

    failures: list[str] = []
    written = 0
    with NewsClient() as client:
        for bucket in buckets:
            for query in bucket.queries:
                try:
                    headlines = client.fetch_query(query, category=bucket.category)
                except NewsHttpError as exc:
                    log.warning("%s %s failed: %s", bucket.category, query, exc)
                    failures.append(f"{bucket.category}:{query}: {exc}")
                    if exc.status_code == 429:
                        raise RuntimeError("Google News RSS rate limited") from exc
                    continue
                except (NewsError, ValueError) as exc:
                    log.warning("%s %s failed: %s", bucket.category, query, exc)
                    failures.append(f"{bucket.category}:{query}: {exc}")
                    continue
                with session_scope() as session:
                    written += upsert_news(session, headlines)

    if written == 0:
        raise RuntimeError(f"no news rows written; failures={failures}")
    return {"news_rows": written, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Google News RSS for catalog queries.")
    parser.add_argument("--categories", help="Optional comma-separated buckets.")
    args = parser.parse_args()
    selected = None
    if args.categories:
        selected = {part.strip().lower() for part in args.categories.split(",") if part.strip()}
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"news_rows": 0, "failures": []}
    try:
        result = ingest(categories=selected)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("news_rows") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_news failed")
        raise SystemExit(1) from exc

    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["news_rows"]),
        extra={"failures": result["failures"], "source": "google_news"},
    )
    log.info(
        "ingest_news rows=%s failures=%s",
        result["news_rows"],
        len(result["failures"]) if isinstance(result["failures"], list) else result["failures"],
    )


if __name__ == "__main__":
    sys.exit(main())
