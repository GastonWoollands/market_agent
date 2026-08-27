"""Evidence pack from Postgres rows. The Outlook agent only narrates this JSON."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from analytics.macro_pack import named_facts, series_row
from analytics.outlook_judgment import build_judgment
from analytics.risk_on import (
    CURVE_SERIES,
    CYCLICALS,
    DEFENSIVES,
    RISK_ON_TICKERS,
    VIX_SERIES,
    compute_risk_on,
)
from store.catalog import load_fred_series, load_polymarket
from store.models import BarDaily, MacroObservation, NewsItem, OddsSnapshot, QuoteLatest, RrgPoint
from store.repos import (
    closes_for_tickers,
    event_count_for_source,
    latest_jobs,
    latest_news,
    latest_odds,
    latest_return_stats,
    latest_rrg_points,
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
EVENTS_NEAR_DAYS = 10
NEAR_CATALYST_KINDS = frozenset({"fomc", "cpi", "pce", "nfp", "central_bank"})
NEWS_LIMIT = 80
NEWS_PER_CATEGORY = 3
MACRO_HISTORY_DAYS = 450
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


def partition_events(
    rows: list[dict[str, Any]], as_of: date, *, near_days: int = EVENTS_NEAR_DAYS
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """10-day window plus the next FOMC/CPI/PCE/NFP/central_bank if later."""
    near_end = as_of + timedelta(days=near_days)
    near: list[dict[str, Any]] = []
    later: list[dict[str, Any]] = []
    have_kind: set[str] = set()
    for row in rows:
        raw = row.get("date")
        try:
            day = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
        except ValueError:
            later.append(row)
            continue
        kind = str(row.get("kind") or "")
        if day <= near_end:
            near.append(row)
            have_kind.add(kind)
        elif kind in NEAR_CATALYST_KINDS and kind not in have_kind:
            near.append(row)
            have_kind.add(kind)
        else:
            later.append(row)
    return near, later


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
    facts: dict[str, Any] | None = None,
    events_later: list[dict[str, Any]] | None = None,
    judgment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "as_of": as_of.isoformat(),
        "header": header,
        "sectors": movers,
        "macro": macro,
        "facts": facts or {},
        "judgment": judgment or {},
        "risk_on": risk_on,
        "odds": odds,
        "rrg": movers,
        "news": news,
        "events": events,
        "events_later": events_later or [],
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
    macro_start = as_of - timedelta(days=MACRO_HISTORY_DAYS)
    macro = [
        series_row(
            item,
            macro_observations(session, item.id, start=macro_start),
            as_of=as_of,
        )
        for item in load_fred_series().series
    ]
    odds = _odds_dicts(latest_odds(session))
    news = _news_dicts(latest_news(session, limit=NEWS_LIMIT))
    rows = [
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
    events, events_later = partition_events(rows, as_of)
    watchlist = [
        {
            "ticker": row.ticker,
            "change_pct": _num(row.quote_change_pct),
            "price": _num(row.quote_price or row.last_close),
        }
        for row in live_tape_rows(session, "watchlist")
    ]
    sources = source_dicts(sources_from_counts(latest_jobs(session), store_counts(session)))
    risk_on = _risk_on(session, as_of)
    facts = named_facts(macro)
    return assemble_pack(
        as_of=as_of,
        header=header,
        movers=movers,
        macro=macro,
        risk_on=risk_on,
        odds=odds,
        news=news,
        events=events,
        watchlist=watchlist,
        sources=sources,
        facts=facts,
        events_later=events_later,
        judgment=build_judgment(
            facts=facts,
            macro=macro,
            odds=odds,
            events=events,
            risk_on=risk_on,
        ),
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


def short_outcome(question: str) -> str:
    text = question.strip()
    lower = text.lower()
    if "no change" in lower:
        return "Hold"
    if "no fed rate cuts" in lower or "no cuts" in lower:
        return "No 2026 cuts"
    if "decrease" in lower and "25" in lower:
        return "Cut 25bp"
    if "increase" in lower and "50" in lower:
        return "Hike 50+"
    if "increase" in lower:
        return "Hike"
    if "recession" in lower:
        return "Recession"
    cleaned = text.replace("Will ", "").replace("?", "").strip()
    return cleaned[:48] if cleaned else text[:48]


WRITER_SERIES = frozenset(
    {
        "DGS2",
        "DGS10",
        "DGS30",
        "T10Y2Y",
        "DFII10",
        "T10YIE",
        "DFF",
        "CPIAUCSL",
        "PCEPILFE",
        "PAYEMS",
        "ICSA",
        "UNRATE",
        "GFDEGDQ188S",
        "BAMLH0A0HYM2",
        "BAMLC0A0CM",
    }
)


def writer_pack(pack: dict[str, Any]) -> dict[str, Any]:
    macro = [row for row in pack.get("macro") or [] if isinstance(row, dict)]
    spine = [
        row
        for row in macro
        if row.get("spine") or row.get("series_id") in WRITER_SERIES
    ]
    return {
        "as_of": pack.get("as_of"),
        "facts": pack.get("facts") or {},
        "judgment": pack.get("judgment") or {},
        "macro": spine or macro,
        "odds": pack.get("odds") or [],
        "events": pack.get("events") or [],
        "risk_on": pack.get("risk_on"),
        "rrg": pack.get("rrg") or [],
        "header": pack.get("header") or [],
        "news": (pack.get("news") or [])[:5],
    }


def _odds_outcomes(raw: dict[str, Any] | None, fallback: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return out
    for market in raw.get("markets") or []:
        if not isinstance(market, dict) or market.get("yes") is None:
            continue
        yes = _num(Decimal(str(market["yes"])))
        if yes is None:
            continue
        question = str(market.get("question") or fallback)
        out.append(
            {
                "label": short_outcome(question),
                "implied_yes": yes,
            }
        )
    out.sort(key=lambda item: item["implied_yes"] or 0, reverse=True)
    return out


def _odds_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    catalog = load_polymarket()
    by_slug = {row.slug: row for row in rows}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in catalog.events:
        row = by_slug.get(event.slug)
        if row is None:
            continue
        seen.add(event.slug)
        label = event.short_label or event.label
        raw = row.raw if isinstance(row.raw, dict) else {}
        if raw.get("closed"):
            continue
        implied = _num(row.implied_yes)
        if not event.show_on_live and any(
            item.get("category") == event.category and item.get("implied_yes") == implied
            for item in out
        ):
            continue
        outcomes = _odds_outcomes(raw, label)
        top = outcomes[0] if outcomes else None
        out.append(
            {
                "slug": event.slug,
                "label": label,
                "category": event.category,
                "implied_yes": implied,
                "as_of": row.as_of.isoformat(),
                "outcomes": outcomes,
                "top_outcome": top["label"] if top else None,
                "top_implied_yes": top["implied_yes"] if top else None,
            }
        )
    for row in rows:
        if row.slug in seen:
            continue
        raw = row.raw if isinstance(getattr(row, "raw", None), dict) else {}
        if raw.get("closed"):
            continue
        outcomes = _odds_outcomes(raw, row.question)
        top = outcomes[0] if outcomes else None
        out.append(
            {
                "slug": row.slug,
                "label": row.question,
                "category": None,
                "implied_yes": _num(row.implied_yes),
                "as_of": row.as_of.isoformat(),
                "outcomes": outcomes,
                "top_outcome": top["label"] if top else None,
                "top_implied_yes": top["implied_yes"] if top else None,
            }
        )
    return out


def _news_dicts(items: list[Any]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for item in items:
        used = counts.get(item.category, 0)
        if used >= NEWS_PER_CATEGORY:
            continue
        counts[item.category] = used + 1
        out.append(
            {
                "title": item.title,
                "publisher": item.publisher,
                "published_at": item.published_at.isoformat(),
                "category": item.category,
                "url": item.url,
            }
        )
    return out


def _num(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)
