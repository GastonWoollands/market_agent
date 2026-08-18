from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import delete, func, select, text

from ingest.retry import http_get, retry_call, retryable_status
from ingest.yahoo.errors import YahooHttpError
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import DailyBar, IntradayBar
from store.catalog import CatalogInstrument
from store.engine import session_scope
from store.models import BarDaily, BarIntraday, Instrument
from store.repos import (
    upsert_daily_bars,
    upsert_instrument,
    upsert_intraday_bars,
)


def test_retryable_status_never_retries_429() -> None:
    assert retryable_status(429) is False
    assert retryable_status(None) is True
    assert retryable_status(503) is True
    assert retryable_status(400) is False


def test_retry_call_retries_timeout_then_succeeds() -> None:
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise YahooHttpError("timeout")
        return "ok"

    result = retry_call(
        once,
        retryable=lambda exc: isinstance(exc, YahooHttpError),
        sleep=lambda _: None,
    )
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_call_does_not_retry_429() -> None:
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        raise YahooHttpError("rate limited", status_code=429)

    with pytest.raises(YahooHttpError):
        retry_call(
            once,
            retryable=lambda exc: isinstance(exc, YahooHttpError)
            and retryable_status(exc.status_code),
            sleep=lambda _: None,
        )
    assert calls["n"] == 1


def test_http_get_retries_503_then_returns() -> None:
    class FakeHttp:
        def __init__(self) -> None:
            self.n = 0

        def get(self, url: str, params: object = None) -> httpx.Response:
            self.n += 1
            request = httpx.Request("GET", url)
            status = 503 if self.n < 2 else 200
            return httpx.Response(status, request=request, text="ok")

    http = FakeHttp()
    bucket = TokenBucket(rate=100.0, burst=5)
    response = http_get(http, bucket, "https://example.test/x", sleep=lambda _: None)  # type: ignore[arg-type]
    assert response.status_code == 200
    assert http.n == 2


def test_http_get_returns_429_without_retry() -> None:
    class FakeHttp:
        def __init__(self) -> None:
            self.n = 0

        def get(self, url: str, params: object = None) -> httpx.Response:
            self.n += 1
            request = httpx.Request("GET", url)
            return httpx.Response(429, request=request, text="no")

    http = FakeHttp()
    bucket = TokenBucket(rate=100.0, burst=5)
    response = http_get(http, bucket, "https://example.test/x", sleep=lambda _: None)  # type: ignore[arg-type]
    assert response.status_code == 429
    assert http.n == 1


def _postgres_up() -> bool:
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _postgres_up(), reason="postgres not available")
def test_yahoo_rerun_does_not_duplicate_daily_or_intraday_bars() -> None:
    ticker = "ZZHDN"
    item = CatalogInstrument(ticker=ticker, yahoo=ticker, name="Hardening fixture")
    day = date(2024, 1, 2)
    daily = DailyBar(
        yahoo_symbol=ticker,
        date=day,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        adj_close=Decimal("1"),
        volume=1,
    )
    ts = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    intra = IntradayBar(
        yahoo_symbol=ticker,
        ts=ts,
        interval="5m",
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=1,
    )
    with session_scope() as session:
        instrument = upsert_instrument(session, item)
        session.flush()
        iid = instrument.id
        upsert_daily_bars(session, iid, [daily])
        upsert_daily_bars(session, iid, [daily])
        upsert_intraday_bars(session, iid, [intra])
        upsert_intraday_bars(session, iid, [intra])
        daily_n = session.execute(
            select(func.count()).select_from(BarDaily).where(BarDaily.instrument_id == iid)
        ).scalar_one()
        intra_n = session.execute(
            select(func.count())
            .select_from(BarIntraday)
            .where(BarIntraday.instrument_id == iid)
        ).scalar_one()
        session.execute(delete(BarIntraday).where(BarIntraday.instrument_id == iid))
        session.execute(delete(BarDaily).where(BarDaily.instrument_id == iid))
        session.execute(delete(Instrument).where(Instrument.id == iid))
    assert daily_n == 1
    assert intra_n == 1
