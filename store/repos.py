from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from store.canonical import DailyBar, QuoteSnapshot
from store.catalog import CatalogInstrument
from store.models import BarDaily, Instrument, JobRun, QuoteLatest, Universe, UniverseMember


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
