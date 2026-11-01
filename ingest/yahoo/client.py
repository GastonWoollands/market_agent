from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError

from ingest.retry import retry_call, retryable_status
from ingest.yahoo.errors import YahooError, YahooHttpError, YahooParseError
from ingest.yahoo.parse import (
    bars_from_history,
    bars_from_intraday,
    option_quotes_from_frame,
    snapshot_from_chart_meta,
    underlying_from_quote,
)
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import DailyBar, IntradayBar, OptionQuote, OptionUnderlying, QuoteSnapshot


def _chrome_session() -> Any:
    try:
        from curl_cffi.requests import Session
    except ImportError as exc:
        raise YahooError(
            "curl_cffi is required for Yahoo ingest; yfinance must not fall back to requests"
        ) from exc
    return Session(impersonate="chrome")


class YahooClient:
    def __init__(
        self,
        *,
        rate: float = 1.0,
        timeout: float = 20.0,
        session: Any | None = None,
    ) -> None:
        self._bucket = TokenBucket(rate=rate, burst=5)
        self._timeout = timeout
        self._owns_session = session is None
        self._session = session or _chrome_session()
        self._tickers: dict[str, yf.Ticker] = {}

    def close(self) -> None:
        if self._owns_session and hasattr(self._session, "close"):
            self._session.close()

    def __enter__(self) -> YahooClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_chart(
        self, symbol: str, *, range_: str = "5y", interval: str = "1d"
    ) -> list[DailyBar]:
        ticker = self._ticker(symbol)
        frame = self._history(
            ticker,
            period=range_,
            interval=interval,
            auto_adjust=False,
            actions=False,
            raise_errors=True,
            timeout=self._timeout,
        )
        return bars_from_history(frame, symbol)

    def fetch_intraday(
        self,
        symbol: str,
        *,
        range_: str = "5d",
        interval: str = "5m",
        prepost: bool = True,
    ) -> list[IntradayBar]:
        ticker = self._ticker(symbol)
        frame = self._history(
            ticker,
            period=range_,
            interval=interval,
            auto_adjust=False,
            actions=False,
            prepost=prepost,
            raise_errors=True,
            timeout=self._timeout,
        )
        return bars_from_intraday(frame, symbol, interval)

    def chart_meta(self, symbol: str) -> dict[str, Any]:
        ticker = self._ticker(symbol)
        meta = getattr(ticker, "history_metadata", None) or {}
        return dict(meta)

    def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteSnapshot]:
        snapshots: list[QuoteSnapshot] = []
        for symbol in symbols:
            ticker = self._ticker(symbol)
            meta = getattr(ticker, "history_metadata", None) or {}
            has_session_prev = bool(
                meta.get("previousClose") or meta.get("regularMarketPreviousClose")
            )
            if not meta.get("regularMarketPrice") or not has_session_prev:
                try:
                    self._history(
                        ticker,
                        period="1d",
                        interval="1d",
                        auto_adjust=False,
                        actions=False,
                        raise_errors=True,
                        timeout=self._timeout,
                    )
                except YahooParseError:
                    continue
                meta = getattr(ticker, "history_metadata", None) or {}
            snap = snapshot_from_chart_meta(symbol, meta)
            if snap is not None:
                snapshots.append(snap)
        return snapshots

    def fetch_option_expiries(self, symbol: str) -> list[date]:
        """Listed expiries (one request). Empty when the name has no listed options."""
        ticker = self._ticker(symbol)
        raw = self._call(lambda: ticker.options)
        return [date.fromisoformat(value) for value in raw]

    def fetch_option_chain(
        self, symbol: str, expiry: date
    ) -> tuple[OptionUnderlying, list[OptionQuote]]:
        """Calls and puts for one expiry plus the underlying quote that ships with it."""
        ticker = self._ticker(symbol)
        chain = self._call(lambda: ticker.option_chain(expiry.isoformat()))
        underlying = underlying_from_quote(symbol, getattr(chain, "underlying", None))
        quotes = option_quotes_from_frame(chain.calls, symbol, expiry, "C")
        quotes += option_quotes_from_frame(chain.puts, symbol, expiry, "P")
        return underlying, quotes

    def _history(self, ticker: Any, **kwargs: Any) -> Any:
        return self._call(lambda: ticker.history(**kwargs))

    def _call(self, fn: Callable[[], Any]) -> Any:
        def once() -> Any:
            self._bucket.acquire()
            try:
                return fn()
            except YFRateLimitError as exc:
                raise YahooHttpError("Yahoo rate limited", status_code=429) from exc
            except YFPricesMissingError as exc:
                raise YahooParseError("no prices") from exc
            except YahooHttpError:
                raise
            except Exception as exc:
                raise YahooHttpError(
                    f"request failed ({exc.__class__.__name__})"
                ) from exc

        return retry_call(
            once,
            retryable=lambda exc: isinstance(exc, YahooHttpError)
            and retryable_status(exc.status_code),
        )

    def _ticker(self, symbol: str) -> yf.Ticker:
        cached = self._tickers.get(symbol)
        if cached is None:
            cached = yf.Ticker(symbol, session=self._session)
            self._tickers[symbol] = cached
        return cached
