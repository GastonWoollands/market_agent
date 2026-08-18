from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from ingest.fred import FredClient
from ingest.fred.errors import FredError, FredHttpError
from jobs.runtime import record_job
from store.catalog import load_fred_series
from store.engine import session_scope
from store.repos import observation_count_for_series, upsert_macro_observations, upsert_macro_series
from store.settings import settings

log = logging.getLogger("jobs.ingest_fred")
JOB_NAME = "ingest_fred"
REQUIRED_SERIES = ("DGS10",)
HISTORY_DAYS = 365 * 10


def ingest(*, series_ids: set[str] | None = None) -> dict[str, int | list[str]]:
    catalog = load_fred_series()
    items = list(catalog.series)
    if series_ids:
        wanted = {item.upper() for item in series_ids}
        items = [item for item in items if item.id.upper() in wanted]
    if not items:
        raise RuntimeError("FRED catalog is empty")

    api_key = settings.fred_api_key
    if not api_key.strip():
        raise RuntimeError("FRED_API_KEY is missing — copy .env.example to .env and set the key")

    observation_start = date.today() - timedelta(days=HISTORY_DAYS)
    required = {item.upper() for item in REQUIRED_SERIES}
    if series_ids:
        required &= {item.upper() for item in series_ids}

    with session_scope() as session:
        for item in items:
            upsert_macro_series(session, item)

    failures: list[str] = []
    observation_rows = 0
    rate_limited = False
    with FredClient(api_key) as client:
        for item in items:
            try:
                points = client.fetch_observations(item.id, observation_start=observation_start)
            except FredHttpError as exc:
                log.warning("%s fetch failed: %s", item.id, exc)
                failures.append(f"{item.id}: {exc}")
                if exc.status_code == 429:
                    rate_limited = True
                    break
                continue
            except (FredError, ValueError) as exc:
                log.warning("%s fetch failed: %s", item.id, exc)
                failures.append(f"{item.id}: {exc}")
                continue
            with session_scope() as session:
                observation_rows += upsert_macro_observations(session, points)

    if rate_limited:
        raise RuntimeError("FRED rate limited")

    with session_scope() as session:
        missing_required = [
            series_id
            for series_id in required
            if observation_count_for_series(session, series_id) == 0
        ]
    if missing_required:
        raise RuntimeError(f"required FRED series have no observations: {missing_required}")

    return {"observation_rows": observation_rows, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FRED observations for Live macro levers.")
    parser.add_argument(
        "--series",
        help="Optional comma-separated FRED series ids (default: full catalog).",
    )
    args = parser.parse_args()
    selected = (
        {part.strip().upper() for part in args.series.split(",") if part.strip()}
        if args.series
        else None
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"observation_rows": 0, "failures": []}
    try:
        result = ingest(series_ids=selected)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("observation_rows") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_fred failed")
        raise SystemExit(1) from exc

    failures = result["failures"]
    record_job(
        JOB_NAME,
        status="ok",
        rows_written=int(result["observation_rows"]),
        extra={"failures": failures, "source": "fred"},
    )
    log.info(
        "ingest_fred observations=%s failures=%s",
        result["observation_rows"],
        len(failures) if isinstance(failures, list) else failures,
    )


if __name__ == "__main__":
    sys.exit(main())
