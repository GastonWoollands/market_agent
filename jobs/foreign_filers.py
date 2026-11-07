"""Curated foreign filers inside ingest_sec (Phase 1.15).

`ForeignFilerSync` keeps their identity and `valuation` membership, fills missing CIKs for
stored names, and writes Yahoo TTM points newer than the latest SEC point
(`metric_ttm.source = yahoo`). The SEC pass stays the official source.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from ingest.sec.parse import yahoo_symbol
from ingest.yahoo.client import YahooClient
from ingest.yahoo.errors import YahooError
from ingest.yahoo.statements import StatementTtm
from store.canonical import SecTicker
from store.catalog import CatalogInstrument, ForeignFiler, ValuationConfig
from store.engine import session_scope
from store.models import MetricTtm
from store.repos import (
    ensure_membership,
    instrument_by_ticker,
    instruments_in_universes,
    latest_ttm_as_of,
    prune_metric_ttm,
    set_instrument_cik,
    upsert_instrument,
    upsert_metric_ttm,
    upsert_universe,
)

log = logging.getLogger("jobs.foreign_filers")
# Yahoo ordinary shares ÷ ADR ratio vs SEC dei shares: a wider gap means a wrong ratio.
SHARES_TOLERANCE = Decimal("0.10")


@dataclass
class ForeignFilerReport:
    synced: list[str] = field(default_factory=list)
    cik_filled: list[str] = field(default_factory=list)
    yahoo_written: int = 0
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def as_meta(self) -> dict[str, object]:
        return {
            "foreign_filers": self.synced,
            "cik_filled": self.cik_filled,
            "yahoo_ttm_written": self.yahoo_written,
            "yahoo_skipped": self.skipped,
            "yahoo_warnings": self.warnings,
        }


class ForeignFilerSync:
    def __init__(
        self,
        catalog: ValuationConfig,
        sec_tickers: Iterable[SecTicker],
        *,
        session_factory: Callable[[], AbstractContextManager[Session]] = session_scope,
    ) -> None:
        self._catalog = catalog
        self._session = session_factory
        self._sec = {item.ticker.upper(): item for item in sec_tickers}
        self.report = ForeignFilerReport()

    def selected(self, tickers: set[str] | None) -> list[ForeignFiler]:
        if not tickers:
            return list(self._catalog.foreign_filers)
        wanted = {item.upper() for item in tickers}
        return [item for item in self._catalog.foreign_filers if item.ticker.upper() in wanted]

    def sync_identity(self, universes: tuple[str, ...]) -> list[int]:
        """Upsert curated names as `valuation` members; fill NULL CIKs. Returns curated ids."""
        ids: list[int] = []
        with self._session() as session:
            universe = upsert_universe(session, "valuation", self._catalog.description)
            session.flush()
            for filer in self._catalog.foreign_filers:
                sec = self._sec.get(filer.ticker.upper())
                if sec is None:
                    self.report.failures.append(f"{filer.ticker}: not in SEC ticker list")
                    continue
                instrument = upsert_instrument(
                    session,
                    CatalogInstrument(
                        ticker=filer.ticker,
                        yahoo=filer.yahoo or yahoo_symbol(filer.ticker),
                        name=filer.name,
                        asset_class="equity",
                        exchange=sec.exchange,
                        cik=sec.cik,
                    ),
                )
                session.flush()
                ensure_membership(session, universe.id, instrument.id)
                ids.append(instrument.id)
                self.report.synced.append(filer.ticker)
            for item in instruments_in_universes(session, universes):
                if item.cik or item.asset_class != "equity":
                    continue
                sec = self._sec.get(item.ticker.upper())
                if sec is not None:
                    set_instrument_cik(session, item.id, sec.cik)
                    self.report.cik_filled.append(item.ticker)
        return ids

    def write_yahoo_ttm(self, yahoo: YahooClient, filers: list[ForeignFiler]) -> None:
        for filer in filers:
            try:
                quarters = yahoo.fetch_quarterly_statements(filer.yahoo_symbol)
            except (YahooError, ValueError) as exc:
                self.report.failures.append(f"{filer.ticker}: yahoo statements: {exc}")
                continue
            with self._session() as session:
                instrument = instrument_by_ticker(session, filer.ticker)
                if instrument is None:
                    self.report.skipped.append(f"{filer.ticker}: not stored")
                    continue
                result = StatementTtm.from_quarters(
                    quarters, cik=instrument.cik or "", adr_ratio=filer.adr_ratio
                )
                if result.skipped:
                    self.report.skipped.append(f"{filer.ticker}: {result.skipped}")
                    continue
                sec_as_of = latest_ttm_as_of(session, instrument.id, source="sec")
                sec_row = session.get(MetricTtm, (instrument.id, sec_as_of)) if sec_as_of else None
                points = [
                    item for item in result.points if sec_as_of is None or item.as_of > sec_as_of
                ]
                for point in points:
                    upsert_metric_ttm(session, instrument.id, point, source="yahoo")
                prune_metric_ttm(
                    session, instrument.id, {item.as_of for item in points}, source="yahoo"
                )
                self.report.yahoo_written += len(points)
                self._check_shares(filer, result, None if sec_row is None else sec_row.shares)
        log.info(
            "foreign filers yahoo_ttm=%s skipped=%s",
            self.report.yahoo_written,
            self.report.skipped,
        )

    def _check_shares(
        self, filer: ForeignFiler, result: StatementTtm, sec_shares: Decimal | None
    ) -> None:
        """Warn (never skip) when Yahoo shares ÷ ratio disagree with the SEC count."""
        latest = result.points[-1].shares
        if latest is None or not sec_shares:
            return
        gap = abs(latest - sec_shares) / sec_shares
        if gap > SHARES_TOLERANCE:
            self.report.warnings.append(
                f"{filer.ticker}: shares_mismatch yahoo={latest} sec={sec_shares}"
            )
