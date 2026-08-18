"""Evidence pack from Postgres rows. The Outlook agent only narrates this JSON."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from analytics.risk_on import (
    CURVE_SERIES,
    CYCLICALS,
    DEFENSIVES,
    RISK_ON_TICKERS,
    VIX_SERIES,
    compute_risk_on,
)
from store.models import BarDaily, MacroObservation, NewsItem, OddsSnapshot, QuoteLatest, RrgPoint
from store.repos import (
    closes_for_tickers,
    event_count_for_source,
    latest_jobs,
    latest_news,
    latest_odds,
    latest_return_stats,
    latest_rrg_points,
    live_macro_rows,
    live_tape_rows,
    macro_observations,
    table_count,
    universe_size,
    upcoming_events,
)

SOURCE_KEYS = (
    ("yahoo", "ingest_yahoo", "daily_bars"),
    ("fred", "ingest_fred", "macro_observations"),
    ("polymarket", "ingest_polymarket", "odds_snapshots"),
    ("google_news", "ingest_news", "news_items"),
    ("finnhub", "ingest_calendar", "earnings_events"),
    ("catalysts", "ingest_calendar", "yaml_events"),
    ("dynamics", "compute_dynamics", "rrg_points"),
)
EVENTS_AHEAD_DAYS = 90
NEWS_LIMIT = 20
HEADER_TICKERS = ("^GSPC", "QQQ", "^RUT")


@dataclass(frozen=True)
class SourceRow:
    vendor: str
    job_name: str
    as_of: datetime | None
    status: str | None
    rows: int
    error: str | None = None


def pack_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def sources_from_counts(jobs: list[Any], counts: dict[str, int]) -> list[SourceRow]:
    by_job = {row.job_name: row for row in jobs}
    out: list[SourceRow] = []
    for vendor, job_name, count_key in SOURCE_KEYS:
        job = by_job.get(job_name)
        as_of = None
        status = None
        error = None
        if job is not None:
            as_of = job.finished_at or job.started_at
            status = job.status
            error = job.error
        out.append(
            SourceRow(
                vendor=vendor,
                job_name=job_name,
                as_of=as_of,
                status=status,
                rows=int(counts.get(count_key, 0)),
                error=error,
            )
        )
    return out


def source_dicts(rows: list[SourceRow]) -> list[dict[str, Any]]:
    return [
        {
            "vendor": row.vendor,
            "job_name": row.job_name,
            "as_of": row.as_of.isoformat() if row.as_of else None,
            "status": row.status,
            "rows": row.rows,
            "error": row.error,
        }
        for row in rows
    ]


def assemble_pack(
    *,
    as_of: date,
    header: list[dict[str, Any]],
    movers: list[dict[str, Any]],
    macro: list[dict[str, Any]],
    risk_on: dict[str, Any] | None,
    odds: list[dict[str, Any]],
    news: list[dict[str, Any]],
    events: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "as_of": as_of.isoformat(),
        "header": header,
        "sectors": movers,
        "macro": macro,
        "risk_on": risk_on,
        "odds": odds,
        "rrg": movers,
        "news": news,
        "events": events,
        "watchlist": watchlist,
        "opportunities": [],
        "sources": sources,
    }


def store_counts(session: Session) -> dict[str, int]:
    return {
        "daily_bars": table_count(session, BarDaily),
        "macro_observations": table_count(session, MacroObservation),
        "odds_snapshots": table_count(session, OddsSnapshot),
        "news_items": table_count(session, NewsItem),
        "earnings_events": event_count_for_source(session, "finnhub"),
        "yaml_events": event_count_for_source(session, "yaml"),
        "rrg_points": table_count(session, RrgPoint),
        "quotes": table_count(session, QuoteLatest),
        "tape_instruments": universe_size(session, "tape"),
        "watchlist_instruments": universe_size(session, "watchlist"),
    }


def pack_from_store(session: Session, *, as_of: date) -> dict[str, Any]:
    tape = {row.ticker: row for row in live_tape_rows(session, "tape")}
    header = [_quote_dict(tape[ticker]) for ticker in HEADER_TICKERS if ticker in tape]
    stats = latest_return_stats(session, as_of)
    movers = []
    for instrument, point in latest_rrg_points(session, as_of):
        stat = stats.get(instrument.id)
        movers.append(
            {
                "ticker": instrument.ticker,
                "quadrant": point.quadrant,
                "rs_ratio": _num(point.rs_ratio),
                "ret_1m": _num(stat.ret_1m) if stat else None,
            }
        )
    macro = [
        {
            "series_id": row.series_id,
            "value": _num(row.last),
            "as_of": row.last_date.isoformat() if row.last_date else None,
        }
        for row in live_macro_rows(session)
    ]
    odds = [
        {
            "slug": row.slug,
            "implied_yes": _num(row.implied_yes),
            "as_of": row.as_of.isoformat(),
        }
        for row in latest_odds(session)
    ]
    news = [
        {
            "title": item.title,
            "publisher": item.publisher,
            "published_at": item.published_at.isoformat(),
            "category": item.category,
            "url": item.url,
        }
        for item in latest_news(session, limit=NEWS_LIMIT)
    ]
    events = [
        {
            "date": item.date.isoformat(),
            "title": item.title,
            "kind": item.kind,
            "ticker": item.ticker,
            "source": item.source,
        }
        for item in upcoming_events(
            session, start=as_of, end=as_of + timedelta(days=EVENTS_AHEAD_DAYS)
        )
    ]
    watchlist = [
        {
            "ticker": row.ticker,
            "change_pct": _num(row.quote_change_pct),
            "price": _num(row.quote_price or row.last_close),
        }
        for row in live_tape_rows(session, "watchlist")
    ]
    sources = source_dicts(sources_from_counts(latest_jobs(session), store_counts(session)))
    return assemble_pack(
        as_of=as_of,
        header=header,
        movers=movers,
        macro=macro,
        risk_on=_risk_on(session, as_of),
        odds=odds,
        news=news,
        events=events,
        watchlist=watchlist,
        sources=sources,
    )


def _quote_dict(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "price": _num(row.quote_price or row.last_close),
        "change_pct": _num(row.quote_change_pct),
    }


def _risk_on(session: Session, as_of: date) -> dict[str, Any] | None:
    start = as_of - timedelta(days=400)
    closes = closes_for_tickers(session, RISK_ON_TICKERS, start=start)

    def series(name: str) -> list[tuple[date, float]]:
        return [(day, float(value)) for day, value in closes.get(name, [])]

    result = compute_risk_on(
        vix=_macro_floats(session, VIX_SERIES, start),
        hyg=series("HYG"),
        lqd=series("LQD"),
        rsp=series("RSP"),
        spy=series("SPY"),
        curve=_macro_floats(session, CURVE_SERIES, start),
        cyclicals={name: series(name) for name in CYCLICALS},
        defensives={name: series(name) for name in DEFENSIVES},
        now=as_of,
    )
    if result.score is None and result.as_of is None:
        return None
    return {
        "score": None if result.score is None else round(result.score, 4),
        "as_of": result.as_of.isoformat() if result.as_of else None,
        "stale": result.stale,
        "factors": {
            name: None if value is None else round(value, 4)
            for name, value in result.factors.items()
        },
    }


def _macro_floats(session: Session, series_id: str, start: date) -> list[tuple[date, float]]:
    return [
        (day, float(value)) for day, value in macro_observations(session, series_id, start=start)
    ]


def _num(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)
