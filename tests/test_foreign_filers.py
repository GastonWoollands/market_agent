"""Curated foreign filers in ingest_sec (Phase 1.15). Postgres, rolled back; no network."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from jobs.foreign_filers import ForeignFilerSync
from store.canonical import MetricTtm as TtmSnapshot
from store.canonical import QuarterlyStatement, SecTicker
from store.catalog import CatalogInstrument, ForeignFiler, ValuationConfig
from store.engine import engine
from store.models import MetricTtm, Universe, UniverseMember
from store.repos import (
    ensure_membership,
    instrument_by_ticker,
    prune_metric_ttm,
    upsert_instrument,
    upsert_metric_ttm,
    upsert_universe,
)


def _postgres_up() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_up(), reason="postgres not available")


@pytest.fixture
def session() -> Iterator[Session]:
    """One outer transaction for the whole test, rolled back at the end."""
    with engine.connect() as conn:
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()


def _factory(db: Session):
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db
        db.flush()

    return scope


def _snap(as_of: str, revenue: int = 100, shares: int | None = 1_000) -> TtmSnapshot:
    return TtmSnapshot(
        cik="0000000001",
        as_of=date.fromisoformat(as_of),
        revenue=Decimal(revenue),
        shares=None if shares is None else Decimal(shares),
    )


def _instrument(db: Session, ticker: str, cik: str | None = None) -> int:
    item = CatalogInstrument(ticker=ticker, yahoo=ticker, name=f"{ticker} fixture", cik=cik)
    instrument = upsert_instrument(db, item)
    db.flush()
    return instrument.id


def _sources(db: Session, instrument_id: int) -> dict[date, str]:
    rows = db.execute(select(MetricTtm).where(MetricTtm.instrument_id == instrument_id)).scalars()
    return {row.as_of: row.source for row in rows}


def test_each_source_prunes_only_its_own_rows(session: Session) -> None:
    instrument_id = _instrument(session, "ZZFPA")
    upsert_metric_ttm(session, instrument_id, _snap("2025-12-31"))
    upsert_metric_ttm(session, instrument_id, _snap("2026-06-30"), source="yahoo")
    session.flush()

    prune_metric_ttm(session, instrument_id, set())
    assert _sources(session, instrument_id) == {date(2026, 6, 30): "yahoo"}

    upsert_metric_ttm(session, instrument_id, _snap("2025-12-31"))
    prune_metric_ttm(session, instrument_id, set(), source="yahoo")
    assert _sources(session, instrument_id) == {date(2025, 12, 31): "sec"}


def test_a_filing_on_the_same_period_replaces_the_vendor_row(session: Session) -> None:
    instrument_id = _instrument(session, "ZZFPB")
    upsert_metric_ttm(session, instrument_id, _snap("2026-06-30"), source="yahoo")
    upsert_metric_ttm(session, instrument_id, _snap("2026-06-30", revenue=120))
    session.flush()
    row = session.get(MetricTtm, (instrument_id, date(2026, 6, 30)))
    assert row is not None and row.source == "sec" and row.revenue == Decimal(120)


def test_unknown_source_is_rejected(session: Session) -> None:
    instrument_id = _instrument(session, "ZZFPC")
    with pytest.raises(ValueError):
        upsert_metric_ttm(session, instrument_id, _snap("2026-06-30"), source="fmp")


class _FakeYahoo:
    def __init__(self, quarters: list[QuarterlyStatement]) -> None:
        self._quarters = quarters

    def fetch_quarterly_statements(self, symbol: str) -> list[QuarterlyStatement]:
        return [item.model_copy(update={"symbol": symbol}) for item in self._quarters]


def _quarters(currency: str = "USD", shares: int = 1_000) -> list[QuarterlyStatement]:
    ends = ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    return [
        QuarterlyStatement(
            symbol="X",
            period_end=date.fromisoformat(end),
            currency=currency,
            revenue=Decimal(25),
            ordinary_shares=Decimal(shares),
        )
        for end in ends
    ]


def _catalog(ticker: str, *, adr_ratio: int = 1) -> ValuationConfig:
    return ValuationConfig(
        foreign_filers=[ForeignFiler(ticker=ticker, name="Fixture", adr_ratio=adr_ratio)]
    )


def test_yahoo_writes_only_periods_newer_than_sec(session: Session) -> None:
    instrument_id = _instrument(session, "ZZFPD", cik="0000000001")
    upsert_metric_ttm(session, instrument_id, _snap("2025-12-31"))
    # A stale vendor row that the SEC point now covers must go.
    upsert_metric_ttm(session, instrument_id, _snap("2025-09-30"), source="yahoo")
    session.flush()

    sync = ForeignFilerSync(_catalog("ZZFPD"), [], session_factory=_factory(session))
    sync.write_yahoo_ttm(_FakeYahoo(_quarters()), sync.selected(None))

    assert _sources(session, instrument_id) == {
        date(2025, 12, 31): "sec",
        date(2026, 3, 31): "yahoo",
        date(2026, 6, 30): "yahoo",
    }
    assert sync.report.yahoo_written == 2
    assert sync.report.warnings == []


def test_wrong_adr_ratio_warns_but_still_writes(session: Session) -> None:
    instrument_id = _instrument(session, "ZZFPE", cik="0000000001")
    upsert_metric_ttm(session, instrument_id, _snap("2025-12-31", shares=1_000))
    session.flush()

    sync = ForeignFilerSync(_catalog("ZZFPE"), [], session_factory=_factory(session))
    sync.write_yahoo_ttm(_FakeYahoo(_quarters(shares=25_000)), sync.selected(None))

    assert sync.report.yahoo_written == 2
    assert sync.report.warnings and "shares_mismatch" in sync.report.warnings[0]


def test_non_usd_statements_write_nothing(session: Session) -> None:
    instrument_id = _instrument(session, "ZZFPF", cik="0000000001")
    sync = ForeignFilerSync(_catalog("ZZFPF"), [], session_factory=_factory(session))
    sync.write_yahoo_ttm(_FakeYahoo(_quarters(currency="ARS")), sync.selected(None))
    assert _sources(session, instrument_id) == {}
    assert sync.report.skipped == ["ZZFPF: non_usd"]


def test_identity_adds_curated_members_and_fills_missing_ciks(session: Session) -> None:
    watch = upsert_universe(session, "watchlist", "User-managed watchlist")
    session.flush()
    ensure_membership(session, watch.id, _instrument(session, "ZZFPW"))
    session.flush()
    listed = [
        SecTicker(cik="0000000042", ticker="ZZFPG", name="Curated", exchange="NYSE"),
        SecTicker(cik="0000000043", ticker="ZZFPW", name="Watched", exchange="Nasdaq"),
    ]

    sync = ForeignFilerSync(_catalog("ZZFPG"), listed, session_factory=_factory(session))
    ids = sync.sync_identity(("valuation", "watchlist"))

    curated = instrument_by_ticker(session, "ZZFPG")
    assert curated is not None and curated.cik == "0000000042"
    assert ids == [curated.id]
    member = session.execute(
        select(UniverseMember)
        .join(Universe, Universe.id == UniverseMember.universe_id)
        .where(Universe.name == "valuation", UniverseMember.instrument_id == curated.id)
    ).scalar_one_or_none()
    assert member is not None
    watched = instrument_by_ticker(session, "ZZFPW")
    assert watched is not None and watched.cik == "0000000043"
    assert "ZZFPW" in sync.report.cik_filled


def test_curated_name_missing_from_sec_is_reported(session: Session) -> None:
    sync = ForeignFilerSync(_catalog("ZZFPX"), [], session_factory=_factory(session))
    assert sync.sync_identity(("valuation",)) == []
    assert sync.report.failures == ["ZZFPX: not in SEC ticker list"]
