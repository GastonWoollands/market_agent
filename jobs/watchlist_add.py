"""Add a watchlist ticker. Yahoo only when the name is missing or has no bars/quote."""

from __future__ import annotations

from store.catalog import CatalogInstrument
from store.engine import session_scope
from store.repos import (
    bar_count_for_ticker,
    ensure_membership,
    instrument_by_ticker,
    upsert_daily_bars,
    upsert_instrument,
    upsert_intraday_bars,
    upsert_quotes,
    upsert_universe,
)
from store.tickers import TickerError, normalize_us_ticker

INTRADAY_RANGE = "5d"


def add_watchlist_ticker(raw: str) -> str:
    ticker = normalize_us_ticker(raw)
    with session_scope() as session:
        existing = instrument_by_ticker(session, ticker)
        instrument_id = existing.id if existing is not None else None
        yahoo_symbol = existing.yahoo_symbol if existing is not None else ticker
        has_bars = bar_count_for_ticker(session, ticker) > 0
        has_quote = False
        if existing is not None:
            from store.models import QuoteLatest

            has_quote = session.get(QuoteLatest, existing.id) is not None

    need_chart = instrument_id is None or not has_bars
    need_quote = not has_quote
    if need_chart or need_quote:
        _hydrate(ticker, yahoo_symbol, need_chart=need_chart, need_quote=need_quote)

    with session_scope() as session:
        instrument = instrument_by_ticker(session, ticker)
        if instrument is None:
            raise TickerError(f"unknown ticker: {ticker}")
        universe = upsert_universe(session, "watchlist", "User-managed watchlist")
        session.flush()
        ensure_membership(session, universe.id, instrument.id)
    return ticker


def _hydrate(ticker: str, yahoo_symbol: str, *, need_chart: bool, need_quote: bool) -> None:
    from ingest.yahoo import YahooClient
    from ingest.yahoo.errors import YahooError, YahooParseError
    from ingest.yahoo.parse import listing_from_chart_meta

    try:
        with YahooClient() as client:
            bars = []
            if need_chart:
                bars = client.fetch_chart(yahoo_symbol, range_="5y")
            meta = client.chart_meta(yahoo_symbol)
            name, exchange = listing_from_chart_meta(ticker, meta)
            quotes = client.fetch_quotes([yahoo_symbol]) if need_quote or need_chart else []
            try:
                intraday = client.fetch_intraday(yahoo_symbol, range_=INTRADAY_RANGE)
            except (YahooError, YahooParseError, ValueError):
                intraday = []
    except YahooParseError as exc:
        raise TickerError(str(exc)) from exc
    except YahooError as exc:
        raise TickerError(str(exc)) from exc

    asset_class = "index" if ticker.startswith("^") else "equity"
    item = CatalogInstrument(
        ticker=ticker,
        yahoo=yahoo_symbol,
        name=name,
        exchange=exchange,
        asset_class=asset_class,
    )
    with session_scope() as session:
        existing = instrument_by_ticker(session, ticker)
        if existing is None:
            instrument = upsert_instrument(session, item)
            session.flush()
        else:
            instrument = existing
        if bars:
            upsert_daily_bars(session, instrument.id, bars)
        if quotes:
            mapped = [
                (instrument.id, snap) for snap in quotes if snap.yahoo_symbol == yahoo_symbol
            ]
            upsert_quotes(session, mapped)
        if intraday:
            upsert_intraday_bars(session, instrument.id, intraday)
