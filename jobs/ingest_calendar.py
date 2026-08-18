from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ingest.finnhub import FinnhubClient
from ingest.finnhub.errors import FinnhubError, FinnhubHttpError
from jobs.runtime import record_job
from store.canonical import CalendarEvent
from store.catalog import CatalystsFile, load_catalysts, load_universes
from store.engine import session_scope
from store.repos import event_count_for_source, upsert_events
from store.settings import settings

log = logging.getLogger("jobs.ingest_calendar")
JOB_NAME = "ingest_calendar"
ET = ZoneInfo("America/New_York")
EARNINGS_DAYS = 14
YAML_KINDS = {"fomc", "cpi", "election", "other"}


def events_from_yaml(catalog: CatalystsFile) -> list[CalendarEvent]:
    out: list[CalendarEvent] = []
    for item in catalog.fomc:
        extra = {"sep": True} if item.sep else None
        out.append(
            CalendarEvent(
                slug=f"yaml:{item.date.isoformat()}:fomc",
                date=item.date,
                title=item.title,
                kind="fomc",
                source="yaml",
                extra=extra,
            )
        )
    for item in catalog.cpi:
        out.append(
            CalendarEvent(
                slug=f"yaml:{item.date.isoformat()}:cpi",
                date=item.date,
                title=item.title,
                kind="cpi",
                source="yaml",
            )
        )
    for item in catalog.other:
        kind = item.type if item.type in YAML_KINDS else "other"
        out.append(
            CalendarEvent(
                slug=f"yaml:{item.date.isoformat()}:{kind}",
                date=item.date,
                title=item.title,
                kind=kind,
                source="yaml",
            )
        )
    return out


def ingest(*, skip_finnhub: bool = False) -> dict[str, int | list[str]]:
    yaml_events = events_from_yaml(load_catalysts())
    if not yaml_events:
        raise RuntimeError("catalysts.yaml is empty")
    with session_scope() as session:
        yaml_rows = upsert_events(session, yaml_events)

    failures: list[str] = []
    earnings_rows = 0
    api_key = settings.finnhub_api_key.strip()
    if skip_finnhub:
        log.info("skipping Finnhub")
    elif not api_key:
        log.warning("FINNHUB_API_KEY missing — yaml catalysts only")
        failures.append("finnhub: missing API key")
    else:
        watch = {item.ticker.upper() for item in load_universes().watchlist.instruments}
        start = datetime.now(ET).date()
        end = start + timedelta(days=EARNINGS_DAYS)
        try:
            with FinnhubClient(api_key) as client:
                earnings = client.fetch_earnings(start=start, end=end, symbols=watch)
        except FinnhubHttpError as exc:
            log.warning("finnhub earnings failed: %s", exc)
            failures.append(str(exc))
            if exc.status_code == 429:
                raise RuntimeError("Finnhub rate limited") from exc
        except (FinnhubError, ValueError) as exc:
            log.warning("finnhub earnings failed: %s", exc)
            failures.append(str(exc))
        else:
            with session_scope() as session:
                earnings_rows = upsert_events(session, earnings)

    with session_scope() as session:
        if event_count_for_source(session, "yaml") == 0:
            raise RuntimeError("no yaml catalyst rows")

    return {
        "yaml_rows": yaml_rows,
        "earnings_rows": earnings_rows,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upsert yaml catalysts and Finnhub watchlist earnings."
    )
    parser.add_argument("--skip-finnhub", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"yaml_rows": 0, "earnings_rows": 0, "failures": []}
    try:
        result = ingest(skip_finnhub=args.skip_finnhub)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("yaml_rows") or 0) + int(result.get("earnings_rows") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_calendar failed")
        raise SystemExit(1) from exc

    written = int(result["yaml_rows"]) + int(result["earnings_rows"])
    record_job(
        JOB_NAME,
        status="ok",
        rows_written=written,
        extra={
            "yaml_rows": result["yaml_rows"],
            "earnings_rows": result["earnings_rows"],
            "failures": result["failures"],
            "source": "calendar",
        },
    )
    log.info(
        "ingest_calendar yaml=%s earnings=%s failures=%s",
        result["yaml_rows"],
        result["earnings_rows"],
        len(result["failures"]) if isinstance(result["failures"], list) else result["failures"],
    )


if __name__ == "__main__":
    sys.exit(main())
