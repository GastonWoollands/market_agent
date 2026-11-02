"""Yahoo option chains for the options scope, then the daily options read per name.

Scope (Northstar §6): watchlist ∪ Opportunities top 25 ∪ SPY / QQQ / IWM ∪ tape sector and
group ETFs. Per name: one request for the expiry list, one per expiry. Expiries are the
nearest four monthlies at least a week out, plus the first expiry after the next earnings
date when it falls inside that window. Strikes within ±30% of spot are stored.

Writes `option_chain_snapshot` (with our Black-Scholes IV) and `option_stats`.
Run after `ingest_yahoo` (adjusted closes for 1y realized vol) and `ingest_fred` (DGS3MO).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from analytics.corr import daily_returns
from analytics.options import (
    EARNINGS_WINDOW_DAYS,
    Quote,
    monthly_expiries,
    solve_ivs,
    summarize,
)
from analytics.risk import MIN_OBS_YEAR, YEAR, realized_vol
from ingest.yahoo import YahooClient
from ingest.yahoo.errors import YahooError, YahooHttpError
from jobs.runtime import tracked_job
from store.canonical import OptionQuote, OptionUnderlying
from store.catalog import load_universes
from store.engine import session_scope
from store.repos import (
    adj_closes_for_instrument_ids,
    instrument_by_ticker,
    instruments_in_universe,
    macro_observations,
    replace_option_chain,
    top_opportunity_instrument_ids,
    upsert_option_stats,
)

log = logging.getLogger("jobs.ingest_options")
JOB_NAME = "ingest_options"
ET = ZoneInfo("America/New_York")
TOP_OPPORTUNITIES = 25
INDEX_ETFS = ("SPY", "QQQ", "IWM")
ETF_ROLES = ("sector", "group")
BAND = (Decimal("0.7"), Decimal("1.3"))
RISK_FREE_SERIES = "DGS3MO"
LOOKBACK_DAYS = 400


@dataclass(frozen=True)
class OptionName:
    id: int
    ticker: str
    yahoo_symbol: str


def scope(session) -> list[OptionName]:
    found: dict[int, OptionName] = {}

    def add(instrument) -> None:
        if instrument is not None:
            found[instrument.id] = OptionName(
                instrument.id, instrument.ticker, instrument.yahoo_symbol
            )

    tape = load_universes().tape.instruments
    etfs = list(INDEX_ETFS) + [item.ticker for item in tape if item.role in ETF_ROLES]
    for ticker in etfs:
        add(instrument_by_ticker(session, ticker))
    for instrument in instruments_in_universe(session, "watchlist"):
        add(instrument)
    top = set(top_opportunity_instrument_ids(session, TOP_OPPORTUNITIES))
    for instrument in instruments_in_universe(session, "valuation"):
        if instrument.id in top:
            add(instrument)
    return list(found.values())


def fetch_chain(
    client: YahooClient, symbol: str, today: date
) -> tuple[OptionUnderlying, list[OptionQuote]] | None:
    """None when the name has no listed options or no monthly a week out."""
    listed = client.fetch_option_expiries(symbol)
    picked = monthly_expiries(listed, today)
    if not picked:
        return None
    underlying: OptionUnderlying | None = None
    quotes: list[OptionQuote] = []
    for expiry in picked:
        found, rows = client.fetch_option_chain(symbol, expiry)
        underlying = underlying or found
        quotes += rows
    earnings = underlying.earnings_date if underlying else None
    as_of = underlying.as_of if underlying else today
    near = earnings is not None and (earnings - as_of).days <= EARNINGS_WINDOW_DAYS
    if earnings is not None and near and earnings <= picked[-1]:
        first_after = min((day for day in listed if day >= earnings), default=None)
        if first_after is not None and first_after not in picked:
            _found, rows = client.fetch_option_chain(symbol, first_after)
            quotes += rows
    assert underlying is not None
    return underlying, quotes


def ingest(*, tickers: set[str] | None = None, today: date | None = None) -> dict[str, object]:
    today = today or datetime.now(ET).date()
    with session_scope() as session:
        names = scope(session)
        risk_free_points = macro_observations(
            session, RISK_FREE_SERIES, start=today - timedelta(days=30)
        )
    if tickers:
        names = [name for name in names if name.ticker.upper() in tickers]
    if not names:
        raise RuntimeError("options scope is empty")
    if not risk_free_points:
        raise RuntimeError(f"{RISK_FREE_SERIES} missing: run ingest_fred")
    risk_free = float(risk_free_points[-1][1]) / 100
    with session_scope() as session:
        adj = adj_closes_for_instrument_ids(
            session, [name.id for name in names], start=today - timedelta(days=LOOKBACK_DAYS)
        )

    chain_rows = 0
    stats_rows = 0
    skipped: list[str] = []
    failures: list[str] = []
    with YahooClient(rate=2.0) as client:
        for index, name in enumerate(names, start=1):
            try:
                fetched = fetch_chain(client, name.yahoo_symbol, today)
            except YahooHttpError as exc:
                failures.append(f"{name.ticker}: {exc}")
                if exc.status_code == 429:
                    log.warning("Yahoo rate limited at %s; stopping", name.ticker)
                    break
                continue
            except (YahooError, ValueError) as exc:
                failures.append(f"{name.ticker}: {exc}")
                continue
            if fetched is None:
                skipped.append(name.ticker)
                continue
            written = store_name(name, *fetched, risk_free=risk_free, adj=adj.get(name.id, []))
            chain_rows += written
            stats_rows += 1
            if index % 10 == 0:
                log.info("options %s/%s", index, len(names))
    if stats_rows == 0:
        raise RuntimeError(f"no option chains stored; failures={failures[:3]}")
    return {
        "chain_rows": chain_rows,
        "stats_rows": stats_rows,
        "names": len(names),
        "skipped": skipped,
        "failures": failures,
    }


def store_name(
    name: OptionName,
    underlying: OptionUnderlying,
    fetched: list[OptionQuote],
    *,
    risk_free: float,
    adj: list[tuple[date, Decimal]],
) -> int:
    spot = underlying.spot
    low, high = spot * BAND[0], spot * BAND[1]
    kept = [row for row in fetched if low <= row.strike <= high]
    quotes = [
        Quote(
            expiry=row.expiry,
            kind=row.kind,
            strike=float(row.strike),
            bid=_float(row.bid),
            ask=_float(row.ask),
            volume=row.volume,
            open_interest=row.open_interest,
            last=_float(row.last),
            last_trade=row.last_trade_at.astimezone(ET).date() if row.last_trade_at else None,
        )
        for row in kept
    ]
    dividend = float(underlying.dividend_yield or 0)
    ivs = solve_ivs(quotes, float(spot), underlying.as_of, risk_free, dividend)
    values = [float(value) for _day, value in adj[-(YEAR + 1) :] if value and float(value) > 0]
    rv = realized_vol(daily_returns(values), min_obs=MIN_OBS_YEAR)
    read = summarize(
        quotes,
        ivs,
        spot=float(spot),
        as_of=underlying.as_of,
        earnings_date=underlying.earnings_date,
        rv_1y=rv,
    )
    rows = [
        {
            "expiry": row.expiry,
            "kind": row.kind,
            "strike": row.strike,
            "bid": row.bid,
            "ask": row.ask,
            "last": row.last,
            "volume": row.volume,
            "open_interest": row.open_interest,
            "vendor_iv": None if row.vendor_iv is None else round(row.vendor_iv, 6),
            "iv": _dec(iv, 6),
            "last_trade_at": row.last_trade_at,
        }
        for row, iv in zip(kept, ivs, strict=True)
    ]
    stats = {
        "instrument_id": name.id,
        "as_of": underlying.as_of,
        "spot": spot,
        "quote_at": underlying.quote_at,
        "risk_free": _dec(risk_free, 6),
        "atm_iv_30d": _dec(read.atm_iv_30d, 6),
        "atm_iv_90d": _dec(read.atm_iv_90d, 6),
        "term_slope": _dec(read.term_slope, 6),
        "skew_30d": _dec(read.skew_30d, 6),
        "rv_1y": _dec(rv, 6),
        "iv_rv": _dec(read.iv_rv, 6),
        "call_volume": read.call_volume,
        "put_volume": read.put_volume,
        "call_oi": read.call_oi,
        "put_oi": read.put_oi,
        "pc_volume": _dec(read.pc_volume, 4),
        "pc_oi": _dec(read.pc_oi, 4),
        "earnings_date": underlying.earnings_date,
        "earnings_estimate": underlying.earnings_estimate,
        "move_expiry": read.move_expiry,
        "expected_move": _dec(read.expected_move, 6),
        "expiries": read.expiries,
        "contracts": read.contracts,
    }
    with session_scope() as session:
        written = replace_option_chain(session, name.id, underlying.as_of, rows)
        upsert_option_stats(session, [stats])
    return written


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _dec(value: float | None, digits: int) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, digits)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Yahoo option chains + options read.")
    parser.add_argument("--tickers", help="Optional comma-separated subset of the scope.")
    args = parser.parse_args()
    selected = (
        {part.strip().upper() for part in args.tickers.split(",") if part.strip()}
        if args.tickers
        else None
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    try:
        with tracked_job(JOB_NAME) as run:
            result = ingest(tickers=selected)
            run.rows = int(result["chain_rows"]) + int(result["stats_rows"])
            run.extra = {key: value for key, value in result.items()} | {"source": "yahoo"}
            log.info(
                "ingest_options names=%s stats=%s chain_rows=%s skipped=%s failures=%s",
                result["names"],
                result["stats_rows"],
                result["chain_rows"],
                result["skipped"],
                result["failures"],
            )
    except Exception:
        log.exception("ingest_options failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
