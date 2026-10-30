from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ingest.finnhub import FinnhubClient
from ingest.finnhub.errors import FinnhubError, FinnhubHttpError
from jobs.runtime import record_job
from store.catalog import load_universes
from store.engine import session_scope
from store.repos import upsert_news
from store.settings import settings

log = logging.getLogger("jobs.ingest_finnhub_news")
JOB_NAME = "ingest_finnhub_news"
ET = ZoneInfo("America/New_York")
COMPANY_DAYS = 2
COMPANY_CAP = 5


def ingest(*, skip_company: bool = False) -> dict[str, int | list[str]]:
    api_key = settings.finnhub_api_key.strip()
    if not api_key:
        raise RuntimeError("FINNHUB_API_KEY missing")
    symbols = sorted(
        {
            item.ticker.upper()
            for item in load_universes().watchlist.instruments
            if not item.ticker.startswith("^")
        }
    )
    end = datetime.now(ET).date()
    start = end - timedelta(days=COMPANY_DAYS - 1)

    failures: list[str] = []
    wire_rows = 0
    company_rows = 0
    with FinnhubClient(api_key) as client:
        try:
            wire = client.fetch_market_news()
        except FinnhubHttpError as exc:
            if exc.status_code == 429:
                raise RuntimeError("Finnhub rate limited") from exc
            log.warning("finnhub wire failed: %s", exc)
            failures.append(f"wire: {exc}")
        except (FinnhubError, ValueError) as exc:
            log.warning("finnhub wire failed: %s", exc)
            failures.append(f"wire: {exc}")
        else:
            with session_scope() as session:
                wire_rows = upsert_news(session, wire)

        for symbol in [] if skip_company else symbols:
            try:
                rows = client.fetch_company_news(symbol, start=start, end=end, cap=COMPANY_CAP)
            except FinnhubHttpError as exc:
                if exc.status_code == 429:
                    raise RuntimeError("Finnhub rate limited") from exc
                log.warning("finnhub %s failed: %s", symbol, exc)
                failures.append(f"{symbol}: {exc}")
                continue
            except (FinnhubError, ValueError) as exc:
                log.warning("finnhub %s failed: %s", symbol, exc)
                failures.append(f"{symbol}: {exc}")
                continue
            with session_scope() as session:
                company_rows += upsert_news(session, rows)

    if wire_rows + company_rows == 0:
        raise RuntimeError(f"no Finnhub news rows written; failures={failures}")
    return {"wire_rows": wire_rows, "company_rows": company_rows, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Finnhub market news and watchlist company news (with summaries)."
    )
    parser.add_argument("--skip-company", action="store_true", help="Wire only.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, int | list[str]] = {"wire_rows": 0, "company_rows": 0, "failures": []}
    try:
        result = ingest(skip_company=args.skip_company)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("wire_rows") or 0) + int(result.get("company_rows") or 0),
            error=str(exc),
            extra={"failures": result.get("failures", [])},
        )
        log.exception("ingest_finnhub_news failed")
        raise SystemExit(1) from exc

    written = int(result["wire_rows"]) + int(result["company_rows"])
    record_job(
        JOB_NAME,
        status="ok",
        rows_written=written,
        extra={
            "wire_rows": result["wire_rows"],
            "company_rows": result["company_rows"],
            "failures": result["failures"],
            "source": "finnhub_news",
        },
    )
    log.info(
        "ingest_finnhub_news wire=%s company=%s failures=%s",
        result["wire_rows"],
        result["company_rows"],
        len(result["failures"]) if isinstance(result["failures"], list) else result["failures"],
    )


if __name__ == "__main__":
    sys.exit(main())
