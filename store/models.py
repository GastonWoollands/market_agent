from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from store.base import Base


class Instrument(Base):
    __tablename__ = "instrument"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    yahoo_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(32))
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(128))
    cik: Mapped[str | None] = mapped_column(String(10))
    figi: Mapped[str | None] = mapped_column(String(12))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    memberships: Mapped[list["UniverseMember"]] = relationship(back_populates="instrument")


class Universe(Base):
    __tablename__ = "universe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list["UniverseMember"]] = relationship(
        back_populates="universe", cascade="all, delete-orphan"
    )


class UniverseMember(Base):
    __tablename__ = "universe_member"

    universe_id: Mapped[int] = mapped_column(
        ForeignKey("universe.id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id", ondelete="CASCADE"), primary_key=True
    )

    universe: Mapped[Universe] = relationship(back_populates="members")
    instrument: Mapped[Instrument] = relationship(back_populates="memberships")


class JobRun(Base):
    __tablename__ = "job_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any] | None] = mapped_column("meta", JSONB)

    __table_args__ = (
        CheckConstraint("status IN ('running', 'ok', 'error')", name="status"),
    )


class BarDaily(Base):
    __tablename__ = "bar_daily"

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column("o", Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column("h", Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column("l", Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column("c", Numeric(18, 6), nullable=False)
    adj_close: Mapped[Decimal] = mapped_column("adj_c", Numeric(18, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    instrument: Mapped[Instrument] = relationship()


class QuoteLatest(Base):
    __tablename__ = "quote_latest"

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id", ondelete="CASCADE"), primary_key=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    market_state: Mapped[str | None] = mapped_column(String(16))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    instrument: Mapped[Instrument] = relationship()


class MacroSeries(Base):
    __tablename__ = "macro_series"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    fred_id: Mapped[str | None] = mapped_column(String(32))

    observations: Mapped[list["MacroObservation"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class MacroObservation(Base):
    __tablename__ = "macro_observation"

    series_id: Mapped[str] = mapped_column(
        ForeignKey("macro_series.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    series: Mapped[MacroSeries] = relationship(back_populates="observations")


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshot"

    slug: Mapped[str] = mapped_column(String(128), primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    implied_yes: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    liquidity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
