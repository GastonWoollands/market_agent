from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from store.canonical import (
    CalendarEvent,
    DailyBar,
    MacroPoint,
    NewsHeadline,
    OddsPoint,
    QuoteSnapshot,
)
from store.canonical import (
    MetricTtm as TtmSnapshot,
)
from store.catalog import CatalogInstrument, FredSeriesItem
from store.models import (
    BarDaily,
    EventItem,
    EvidencePack,
    Instrument,
    JobRun,
    MacroObservation,
    MacroSeries,
    MetricTtm,
    NewsItem,
    OddsSnapshot,
    OutlookReport,
    QuoteLatest,
    ReturnStats,
    RrgPoint,
    Universe,
    UniverseMember,
)


def upsert_instrument(session: Session, item: CatalogInstrument) -> Instrument:
    stmt = (
        insert(Instrument)
        .values(
            ticker=item.ticker,
            yahoo_symbol=item.yahoo,
            name=item.name,
            exchange=item.exchange,
            asset_class=item.asset_class,
            sector=item.sector,
            industry=item.industry,
            cik=item.cik,
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[Instrument.ticker],
            set_={
                "yahoo_symbol": item.yahoo,
                "name": item.name,
                "exchange": item.exchange,
                "asset_class": item.asset_class,
                "sector": item.sector,
                "industry": item.industry,
                "cik": item.cik,
                "is_active": True,
                "updated_at": func.now(),
            },
        )
        .returning(Instrument)
    )
    return session.scalars(stmt).one()


def upsert_universe(session: Session, name: str, description: str | None) -> Universe:
    stmt = (
        insert(Universe)
        .values(name=name, description=description)
        .on_conflict_do_update(
            index_elements=[Universe.name],
            set_={"description": description},
        )
        .returning(Universe)
    )
    return session.scalars(stmt).one()


def ensure_membership(session: Session, universe_id: int, instrument_id: int) -> None:
    stmt = (
        insert(UniverseMember)
        .values(universe_id=universe_id, instrument_id=instrument_id)
        .on_conflict_do_nothing(index_elements=["universe_id", "instrument_id"])
    )
    session.execute(stmt)


def universe_size(session: Session, name: str) -> int:
    stmt = (
        select(func.count())
        .select_from(UniverseMember)
        .join(Universe, Universe.id == UniverseMember.universe_id)
        .where(Universe.name == name)
    )
    return int(session.execute(stmt).scalar_one())


def latest_jobs(session: Session) -> list[JobRun]:
    latest = (
        select(
            JobRun.job_name,
            func.max(JobRun.started_at).label("started_at"),
        )
        .group_by(JobRun.job_name)
        .subquery()
    )
    stmt = (
        select(JobRun)
        .join(
            latest,
            (JobRun.job_name == latest.c.job_name)
            & (JobRun.started_at == latest.c.started_at),
        )
        .order_by(JobRun.job_name)
    )
    return list(session.execute(stmt).scalars())


def instruments_in_universe(session: Session, name: str) -> list[Instrument]:
    stmt = (
        select(Instrument)
        .join(UniverseMember, UniverseMember.instrument_id == Instrument.id)
        .join(Universe, Universe.id == UniverseMember.universe_id)
        .where(Universe.name == name, Instrument.is_active.is_(True))
        .order_by(Instrument.ticker)
    )
    return list(session.execute(stmt).scalars())


def upsert_daily_bars(
    session: Session,
    instrument_id: int,
    bars: list[DailyBar],
    *,
    source: str = "yahoo",
) -> int:
    if not bars:
        return 0
    rows = [
        {
            "instrument_id": instrument_id,
            "date": bar.date,
            "o": bar.open,
            "h": bar.high,
            "l": bar.low,
            "c": bar.close,
            "adj_c": bar.adj_close,
            "volume": bar.volume,
            "source": source,
        }
        for bar in bars
    ]
    stmt = insert(BarDaily).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "date"],
        set_={
            "o": stmt.excluded.o,
            "h": stmt.excluded.h,
            "l": stmt.excluded.l,
            "c": stmt.excluded.c,
            "adj_c": stmt.excluded.adj_c,
            "volume": stmt.excluded.volume,
            "source": stmt.excluded.source,
        },
    )
    session.execute(stmt)
    return len(rows)


def upsert_quotes(
    session: Session,
    quotes: list[tuple[int, QuoteSnapshot]],
    *,
    source: str = "yahoo",
) -> int:
    if not quotes:
        return 0
    rows = [
        {
            "instrument_id": instrument_id,
            "price": quote.price,
            "change_pct": quote.change_pct,
            "volume": quote.volume,
            "market_state": quote.market_state,
            "as_of": quote.as_of,
            "source": source,
            "updated_at": func.now(),
        }
        for instrument_id, quote in quotes
    ]
    stmt = insert(QuoteLatest).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id"],
        set_={
            "price": stmt.excluded.price,
            "change_pct": stmt.excluded.change_pct,
            "volume": stmt.excluded.volume,
            "market_state": stmt.excluded.market_state,
            "as_of": stmt.excluded.as_of,
            "source": stmt.excluded.source,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)
    return len(rows)


def table_count(session: Session, model: type) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar_one())


def bar_count_for_ticker(session: Session, ticker: str) -> int:
    stmt = (
        select(func.count())
        .select_from(BarDaily)
        .join(Instrument, Instrument.id == BarDaily.instrument_id)
        .where(Instrument.ticker == ticker)
    )
    return int(session.execute(stmt).scalar_one())


@dataclass(frozen=True)
class LiveTapeRow:
    ticker: str
    name: str
    quote_price: Decimal | None
    quote_change_pct: Decimal | None
    market_state: str | None
    as_of: datetime | None
    last_close: Decimal | None
    prev_close: Decimal | None
    last_date: date | None


def live_tape_rows(session: Session, universe: str = "tape") -> list[LiveTapeRow]:
    ranked = (
        select(
            BarDaily.instrument_id,
            BarDaily.close.label("close"),
            BarDaily.date,
            func.row_number()
            .over(partition_by=BarDaily.instrument_id, order_by=BarDaily.date.desc())
            .label("rn"),
        )
    ).subquery()
    last_bar = select(ranked).where(ranked.c.rn == 1).subquery()
    prev_bar = select(ranked).where(ranked.c.rn == 2).subquery()
    stmt = (
        select(
            Instrument.ticker,
            Instrument.name,
            QuoteLatest.price,
            QuoteLatest.change_pct,
            QuoteLatest.market_state,
            QuoteLatest.as_of,
            last_bar.c.close,
            prev_bar.c.close,
            last_bar.c.date,
        )
        .join(UniverseMember, UniverseMember.instrument_id == Instrument.id)
        .join(Universe, Universe.id == UniverseMember.universe_id)
        .outerjoin(QuoteLatest, QuoteLatest.instrument_id == Instrument.id)
        .outerjoin(last_bar, last_bar.c.instrument_id == Instrument.id)
        .outerjoin(prev_bar, prev_bar.c.instrument_id == Instrument.id)
        .where(Universe.name == universe, Instrument.is_active.is_(True))
        .order_by(Instrument.ticker)
    )
    return [
        LiveTapeRow(
            ticker=ticker,
            name=name,
            quote_price=quote_price,
            quote_change_pct=quote_change,
            market_state=market_state,
            as_of=as_of,
            last_close=last_close,
            prev_close=prev_close,
            last_date=last_date,
        )
        for (
            ticker,
            name,
            quote_price,
            quote_change,
            market_state,
            as_of,
            last_close,
            prev_close,
            last_date,
        ) in session.execute(stmt)
    ]


def upsert_macro_series(session: Session, item: FredSeriesItem, *, source: str = "fred") -> None:
    stmt = (
        insert(MacroSeries)
        .values(
            id=item.id,
            name=item.name,
            unit=item.unit,
            source=source,
            fred_id=item.id,
        )
        .on_conflict_do_update(
            index_elements=[MacroSeries.id],
            set_={
                "name": item.name,
                "unit": item.unit,
                "source": source,
                "fred_id": item.id,
            },
        )
    )
    session.execute(stmt)


def upsert_macro_observations(session: Session, points: list[MacroPoint]) -> int:
    if not points:
        return 0
    rows = [
        {"series_id": point.series_id, "date": point.date, "value": point.value} for point in points
    ]
    stmt = insert(MacroObservation).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["series_id", "date"],
        set_={"value": stmt.excluded.value},
    )
    session.execute(stmt)
    return len(rows)


def observation_count_for_series(session: Session, series_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(MacroObservation)
        .where(MacroObservation.series_id == series_id)
    )
    return int(session.execute(stmt).scalar_one())


@dataclass(frozen=True)
class LiveMacroRow:
    series_id: str
    last: Decimal | None
    prev: Decimal | None
    last_date: date | None


def live_macro_rows(session: Session) -> list[LiveMacroRow]:
    ranked = (
        select(
            MacroObservation.series_id,
            MacroObservation.value,
            MacroObservation.date,
            func.row_number()
            .over(
                partition_by=MacroObservation.series_id,
                order_by=MacroObservation.date.desc(),
            )
            .label("rn"),
        )
    ).subquery()
    last_obs = select(ranked).where(ranked.c.rn == 1).subquery()
    prev_obs = select(ranked).where(ranked.c.rn == 2).subquery()
    stmt = (
        select(
            last_obs.c.series_id,
            last_obs.c.value,
            prev_obs.c.value,
            last_obs.c.date,
        ).outerjoin(prev_obs, prev_obs.c.series_id == last_obs.c.series_id)
    )
    return [
        LiveMacroRow(
            series_id=series_id,
            last=last,
            prev=prev,
            last_date=last_date,
        )
        for series_id, last, prev, last_date in session.execute(stmt)
    ]


def macro_observations(
    session: Session,
    series_id: str,
    *,
    start: date | None = None,
) -> list[tuple[date, Decimal]]:
    stmt = select(MacroObservation.date, MacroObservation.value).where(
        MacroObservation.series_id == series_id
    )
    if start is not None:
        stmt = stmt.where(MacroObservation.date >= start)
    stmt = stmt.order_by(MacroObservation.date)
    return [(day, value) for day, value in session.execute(stmt)]


def closes_for_tickers(
    session: Session,
    tickers: Sequence[str],
    *,
    start: date | None = None,
) -> dict[str, list[tuple[date, Decimal]]]:
    if not tickers:
        return {}
    stmt = (
        select(Instrument.ticker, BarDaily.date, BarDaily.close)
        .join(BarDaily, BarDaily.instrument_id == Instrument.id)
        .where(Instrument.ticker.in_(list(tickers)))
    )
    if start is not None:
        stmt = stmt.where(BarDaily.date >= start)
    stmt = stmt.order_by(Instrument.ticker, BarDaily.date)
    out: dict[str, list[tuple[date, Decimal]]] = {ticker: [] for ticker in tickers}
    for ticker, day, close in session.execute(stmt):
        out.setdefault(ticker, []).append((day, close))
    return out


def upsert_odds(session: Session, point: OddsPoint) -> None:
    stmt = (
        insert(OddsSnapshot)
        .values(
            slug=point.slug,
            as_of=point.as_of,
            question=point.question,
            implied_yes=point.implied_yes,
            liquidity=point.liquidity,
            raw=point.raw,
        )
        .on_conflict_do_update(
            index_elements=[OddsSnapshot.slug],
            set_={
                "as_of": point.as_of,
                "question": point.question,
                "implied_yes": point.implied_yes,
                "liquidity": point.liquidity,
                "raw": point.raw,
            },
        )
    )
    session.execute(stmt)


def latest_odds(session: Session) -> list[OddsSnapshot]:
    stmt = select(OddsSnapshot).order_by(OddsSnapshot.slug)
    return list(session.execute(stmt).scalars())


def upsert_rrg_points(
    session: Session,
    rows: Sequence[dict[str, object]],
) -> int:
    if not rows:
        return 0
    stmt = insert(RrgPoint).values(list(rows))
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "as_of"],
        set_={
            "rs_ratio": stmt.excluded.rs_ratio,
            "rs_momentum": stmt.excluded.rs_momentum,
            "quadrant": stmt.excluded.quadrant,
        },
    )
    session.execute(stmt)
    return len(rows)


def upsert_return_stats(
    session: Session,
    rows: Sequence[dict[str, object]],
) -> int:
    if not rows:
        return 0
    stmt = insert(ReturnStats).values(list(rows))
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "as_of"],
        set_={
            "ret_1w": stmt.excluded.ret_1w,
            "ret_1m": stmt.excluded.ret_1m,
            "ret_3m": stmt.excluded.ret_3m,
            "ret_1y": stmt.excluded.ret_1y,
            "indexed": stmt.excluded.indexed,
        },
    )
    session.execute(stmt)
    return len(rows)


def latest_rrg_points(
    session: Session,
    before: date | None = None,
) -> list[tuple[Instrument, RrgPoint]]:
    latest = select(
        RrgPoint.instrument_id,
        func.max(RrgPoint.as_of).label("as_of"),
    )
    if before is not None:
        latest = latest.where(RrgPoint.as_of <= before)
    latest = latest.group_by(RrgPoint.instrument_id).subquery()
    stmt = (
        select(Instrument, RrgPoint)
        .join(RrgPoint, RrgPoint.instrument_id == Instrument.id)
        .join(
            latest,
            (RrgPoint.instrument_id == latest.c.instrument_id)
            & (RrgPoint.as_of == latest.c.as_of),
        )
        .order_by(Instrument.ticker)
    )
    return list(session.execute(stmt).all())


def rrg_trails(
    session: Session,
    instrument_ids: Sequence[int],
    *,
    as_of: date,
    limit: int,
) -> dict[int, list[RrgPoint]]:
    if not instrument_ids:
        return {}
    stmt = (
        select(RrgPoint)
        .where(
            RrgPoint.instrument_id.in_(list(instrument_ids)),
            RrgPoint.as_of <= as_of,
        )
        .order_by(RrgPoint.instrument_id, RrgPoint.as_of)
    )
    grouped: dict[int, list[RrgPoint]] = {}
    for point in session.execute(stmt).scalars():
        grouped.setdefault(point.instrument_id, []).append(point)
    return {iid: points[-limit:] for iid, points in grouped.items()}


def latest_return_stats(session: Session, before: date | None = None) -> dict[int, ReturnStats]:
    stmt = select(ReturnStats)
    if before is not None:
        stmt = stmt.where(ReturnStats.as_of <= before)
    best: dict[int, ReturnStats] = {}
    for row in session.execute(stmt).scalars():
        current = best.get(row.instrument_id)
        if current is None or row.as_of > current.as_of:
            best[row.instrument_id] = row
    return best


def upsert_news(session: Session, headlines: Sequence[NewsHeadline]) -> int:
    if not headlines:
        return 0
    rows = [
        {
            "guid": item.guid,
            "title": item.title,
            "url": item.url,
            "publisher": item.publisher,
            "published_at": item.published_at,
            "category": item.category,
            "query": item.query,
        }
        for item in headlines
    ]
    stmt = insert(NewsItem).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["guid"],
        set_={
            "title": stmt.excluded.title,
            "url": stmt.excluded.url,
            "publisher": stmt.excluded.publisher,
            "published_at": stmt.excluded.published_at,
            "category": stmt.excluded.category,
            "query": stmt.excluded.query,
        },
    )
    session.execute(stmt)
    return len(rows)


def latest_news(
    session: Session,
    *,
    since: datetime | None = None,
    limit: int = 40,
) -> list[NewsItem]:
    stmt = select(NewsItem)
    if since is not None:
        stmt = stmt.where(NewsItem.published_at >= since)
    stmt = stmt.order_by(NewsItem.published_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


def upsert_events(session: Session, events: Sequence[CalendarEvent]) -> int:
    if not events:
        return 0
    rows = [
        {
            "slug": item.slug,
            "date": item.date,
            "title": item.title,
            "kind": item.kind,
            "source": item.source,
            "ticker": item.ticker,
            "extra": item.extra,
        }
        for item in events
    ]
    stmt = insert(EventItem).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug"],
        set_={
            "date": stmt.excluded.date,
            "title": stmt.excluded.title,
            "kind": stmt.excluded.kind,
            "source": stmt.excluded.source,
            "ticker": stmt.excluded.ticker,
            "extra": stmt.excluded.extra,
        },
    )
    session.execute(stmt)
    return len(rows)


def upcoming_events(
    session: Session,
    *,
    start: date,
    end: date,
) -> list[EventItem]:
    stmt = (
        select(EventItem)
        .where(EventItem.date >= start, EventItem.date <= end)
        .order_by(EventItem.date, EventItem.slug)
    )
    return list(session.execute(stmt).scalars())


def event_count_for_source(session: Session, source: str) -> int:
    stmt = select(func.count()).select_from(EventItem).where(EventItem.source == source)
    return int(session.execute(stmt).scalar_one())


def upsert_evidence_pack(
    session: Session,
    *,
    as_of: date,
    pack: dict[str, Any],
    digest: str,
) -> EvidencePack:
    stmt = (
        insert(EvidencePack)
        .values(as_of=as_of, pack=pack, hash=digest, created_at=func.now())
        .on_conflict_do_update(
            index_elements=["as_of"],
            set_={"pack": pack, "hash": digest, "created_at": func.now()},
        )
        .returning(EvidencePack)
    )
    return session.scalars(stmt).one()


def latest_evidence_pack(session: Session, as_of: date | None = None) -> EvidencePack | None:
    stmt = select(EvidencePack)
    if as_of is not None:
        stmt = stmt.where(EvidencePack.as_of == as_of)
    stmt = stmt.order_by(EvidencePack.as_of.desc())
    return session.execute(stmt).scalars().first()


def upsert_outlook_report(
    session: Session,
    *,
    as_of: date,
    model: str,
    prompt_version: str,
    body_md: str,
    body_json: dict[str, Any],
    pack_id: int | None,
    status: str,
) -> OutlookReport:
    stmt = (
        insert(OutlookReport)
        .values(
            as_of=as_of,
            model=model,
            prompt_version=prompt_version,
            body_md=body_md,
            body_json=body_json,
            pack_id=pack_id,
            status=status,
            created_at=func.now(),
        )
        .on_conflict_do_update(
            index_elements=["as_of"],
            set_={
                "model": model,
                "prompt_version": prompt_version,
                "body_md": body_md,
                "body_json": body_json,
                "pack_id": pack_id,
                "status": status,
                "created_at": func.now(),
            },
        )
        .returning(OutlookReport)
    )
    return session.scalars(stmt).one()


def latest_outlook_report(session: Session, as_of: date | None = None) -> OutlookReport | None:
    stmt = select(OutlookReport)
    if as_of is not None:
        stmt = stmt.where(OutlookReport.as_of == as_of)
    stmt = stmt.order_by(OutlookReport.as_of.desc())
    return session.execute(stmt).scalars().first()


def replace_membership(session: Session, universe_id: int, instrument_ids: Sequence[int]) -> int:
    wanted = set(instrument_ids)
    existing = list(
        session.execute(
            select(UniverseMember).where(UniverseMember.universe_id == universe_id)
        ).scalars()
    )
    removed = 0
    for row in existing:
        if row.instrument_id not in wanted:
            session.delete(row)
            removed += 1
    for instrument_id in wanted:
        ensure_membership(session, universe_id, instrument_id)
    return len(wanted)


def upsert_metric_ttm(session: Session, instrument_id: int, item: TtmSnapshot) -> None:
    stmt = insert(MetricTtm).values(
        instrument_id=instrument_id,
        as_of=item.as_of,
        revenue=item.revenue,
        ebitda=item.ebitda,
        fcf=item.fcf,
        net_debt=item.net_debt,
        shares=item.shares,
        source="sec",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "as_of"],
        set_={
            "revenue": stmt.excluded.revenue,
            "ebitda": stmt.excluded.ebitda,
            "fcf": stmt.excluded.fcf,
            "net_debt": stmt.excluded.net_debt,
            "shares": stmt.excluded.shares,
            "source": stmt.excluded.source,
        },
    )
    session.execute(stmt)


def latest_metric_ttm(
    session: Session, universe: str = "valuation"
) -> list[tuple[Instrument, MetricTtm]]:
    ranked = (
        select(
            MetricTtm.instrument_id,
            func.max(MetricTtm.as_of).label("as_of"),
        )
        .group_by(MetricTtm.instrument_id)
        .subquery()
    )
    stmt = (
        select(Instrument, MetricTtm)
        .join(UniverseMember, UniverseMember.instrument_id == Instrument.id)
        .join(Universe, Universe.id == UniverseMember.universe_id)
        .join(MetricTtm, MetricTtm.instrument_id == Instrument.id)
        .join(
            ranked,
            (MetricTtm.instrument_id == ranked.c.instrument_id)
            & (MetricTtm.as_of == ranked.c.as_of),
        )
        .where(Universe.name == universe, Instrument.is_active.is_(True))
        .order_by(MetricTtm.revenue.desc(), Instrument.ticker)
    )
    return list(session.execute(stmt).all())
