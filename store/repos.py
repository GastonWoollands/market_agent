from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from store.canonical import DailyBar, MacroPoint, OddsPoint, QuoteSnapshot
from store.catalog import CatalogInstrument, FredSeriesItem
from store.models import (
    BarDaily,
    Instrument,
    JobRun,
    MacroObservation,
    MacroSeries,
    OddsSnapshot,
    QuoteLatest,
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
