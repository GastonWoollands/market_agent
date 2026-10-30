from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ingest.finnhub import FinnhubClient
from ingest.finnhub.errors import FinnhubError, FinnhubHttpError
from jobs.runtime import record_job
from store.canonical import CalendarEvent
from store.catalog import CatalystItem, CatalystsFile, load_catalysts, load_universes
from store.engine import session_scope
from store.repos import event_count_for_source, upsert_events
from store.settings import settings

log = logging.getLogger("jobs.ingest_calendar")
JOB_NAME = "ingest_calendar"
ET = ZoneInfo("America/New_York")
EARNINGS_DAYS = 14
YAML_KINDS = {
    "fomc",
    "cpi",
    "pce",
    "nfp",
    "gdp",
    "jolts",
    "election",
    "central_bank",
    "speech",
    "minutes",
    "beige_book",
    "ism",
    "treasury",
    "other",
}
TITLE_SLUG_KINDS = frozenset({"speech", "ism", "treasury", "central_bank"})
# Recurring series must stay listed this far ahead; below it the yaml needs its refresh.
HORIZON_DAYS = 60
# One-offs or event-driven slots: no horizon to keep.
NO_HORIZON = frozenset({"speech", "election", "other"})


def short_horizons(events: list[CalendarEvent], today: date) -> list[str]:
    """Recurring series whose last listed date is within HORIZON_DAYS of `today`.

    Central banks are tracked per bank (by title), the rest per kind.
    """
    last: dict[str, date] = {}
    for item in events:
        if item.kind in NO_HORIZON:
            continue
        key = item.title if item.kind == "central_bank" else item.kind
        last[key] = max(last.get(key, item.date), item.date)
    limit = today + timedelta(days=HORIZON_DAYS)
    return [f"{key} (last {day.isoformat()})" for key, day in sorted(last.items()) if day < limit]


def _slug_title(title: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in title)
    return "-".join(part for part in raw.split("-") if part)[:48]


def _event(
    *,
    day: date,
    title: str,
    kind: str,
    extra: dict | None = None,
) -> CalendarEvent:
    slug_kind = f"{kind}:{_slug_title(title)}" if kind in TITLE_SLUG_KINDS else kind
    return CalendarEvent(
        slug=f"yaml:{day.isoformat()}:{slug_kind}",
        date=day,
        title=title,
        kind=kind,
        source="yaml",
        extra=extra,
    )


def events_from_yaml(catalog: CatalystsFile) -> list[CalendarEvent]:
    out: list[CalendarEvent] = []
    def timed(kind: str, item: CatalystItem, extra: dict | None = None) -> dict | None:
        at = item.time or catalog.default_times.get(kind)
        if not at:
            return extra
        return {**(extra or {}), "time_et": at}

    for item in catalog.fomc:
        extra = {"sep": True} if item.sep else None
        out.append(
            _event(day=item.date, title=item.title, kind="fomc", extra=timed("fomc", item, extra))
        )
    for kind, items in (
        ("cpi", catalog.cpi),
        ("pce", catalog.pce),
        ("nfp", catalog.nfp),
        ("gdp", catalog.gdp),
        ("jolts", catalog.jolts),
        ("speech", catalog.speech),
        ("minutes", catalog.minutes),
        ("beige_book", catalog.beige_book),
        ("ism", catalog.ism),
        ("treasury", catalog.treasury),
    ):
        for item in items:
            out.append(
                _event(day=item.date, title=item.title, kind=kind, extra=timed(kind, item))
            )
    for item in catalog.other:
        kind = item.type if item.type in YAML_KINDS else "other"
        out.append(_event(day=item.date, title=item.title, kind=kind, extra=timed(kind, item)))
    return out


def ingest(*, skip_finnhub: bool = False) -> dict[str, int | list[str]]:
    yaml_events = events_from_yaml(load_catalysts())
    if not yaml_events:
        raise RuntimeError("catalysts.yaml is empty")
    horizon = short_horizons(yaml_events, datetime.now(ET).date())
    if horizon:
        log.warning(
            "catalysts.yaml ends within %sd for: %s; add the next official dates",
            HORIZON_DAYS,
            ", ".join(horizon),
        )
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
        "short_horizon": horizon,
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
            "short_horizon": result.get("short_horizon", []),
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
