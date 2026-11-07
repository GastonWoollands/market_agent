import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from store.catalog import CatalogInstrument
from store.engine import engine
from store.repos import (
    ensure_membership,
    universe_equity_tickers,
    upsert_instrument,
    upsert_universe,
)


def _postgres_up() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _postgres_up(), reason="postgres not available")
def test_watchlist_scope_reads_stored_members_not_yaml_seed() -> None:
    """Names added from the UI are not in universes.yaml; jobs must still see them."""
    with Session(engine) as session:
        universe = upsert_universe(session, "watchlist", "User-managed watchlist")
        session.flush()
        for ticker in ("ZZWLA", "^ZZWLI"):
            item = CatalogInstrument(ticker=ticker, yahoo=ticker, name="Watchlist fixture")
            instrument = upsert_instrument(session, item)
            session.flush()
            ensure_membership(session, universe.id, instrument.id)
        session.flush()

        tickers = universe_equity_tickers(session, "watchlist")
        session.rollback()

    assert "ZZWLA" in tickers
    assert "^ZZWLI" not in tickers
    assert tickers == sorted(tickers)
