import json
from datetime import UTC, date, datetime
from decimal import Decimal
from math import isclose
from pathlib import Path

import pytest

from analytics.options import (
    Quote,
    bs_price,
    implied_vol,
    iv_rank,
    monthly_expiries,
    quote_iv,
    solve_ivs,
    summarize,
    term_iv,
)
from ingest.cboe.errors import CboeParseError
from ingest.cboe.parse import stats_from_payload
from ingest.yahoo.parse import underlying_from_quote

AS_OF = date(2026, 10, 30)
FIXTURE = Path(__file__).parent / "fixtures" / "cboe_daily_2026-10-30.json"


def test_implied_vol_round_trips_calls_and_puts() -> None:
    for kind, strike in (("C", 110.0), ("P", 90.0)):
        price = bs_price(kind, 100.0, strike, 0.25, 0.04, 0.01, 0.35)
        assert isclose(
            implied_vol(kind, price, 100.0, strike, 0.25, 0.04, 0.01), 0.35, abs_tol=1e-6
        )
    assert implied_vol("C", 0.0, 100.0, 110.0, 0.25, 0.04, 0.0) is None
    assert implied_vol("C", 150.0, 100.0, 110.0, 0.25, 0.04, 0.0) is None  # above spot


def test_monthly_expiries_third_friday_and_holiday_thursday() -> None:
    listed = [
        date(2026, 11, 6),
        date(2026, 11, 20),
        date(2026, 11, 27),
        date(2026, 12, 18),
        date(2027, 6, 17),  # Juneteenth-style holiday week: Thursday stands in
        date(2027, 1, 15),
    ]
    assert monthly_expiries(listed, AS_OF, count=3) == [
        date(2026, 11, 20),
        date(2026, 12, 18),
        date(2027, 1, 15),
    ]
    assert monthly_expiries(listed, date(2026, 11, 16)) == [
        date(2026, 12, 18),
        date(2027, 1, 15),
        date(2027, 6, 17),
    ]


def _quote(
    kind: str,
    strike: float,
    vol: float = 0.3,
    *,
    expiry: date = date(2026, 11, 29),
    spread: float = 0.02,
    **extra,
) -> Quote:
    t = (expiry - AS_OF).days / 365
    price = bs_price(kind, 100.0, strike, t, 0.04, 0.0, vol)
    return Quote(expiry, kind, strike, price - spread / 2, price + spread / 2, **extra)


def test_quote_iv_otm_only_and_same_session_last_fallback() -> None:
    assert quote_iv(_quote("C", 90.0), 100.0, AS_OF, 0.04, 0.0) is None  # in the money
    assert isclose(quote_iv(_quote("P", 90.0), 100.0, AS_OF, 0.04, 0.0), 0.3, abs_tol=1e-3)
    wide = _quote("C", 110.0, spread=5.0)
    assert quote_iv(wide, 100.0, AS_OF, 0.04, 0.0) is None
    good = _quote("C", 110.0)
    traded = Quote(
        good.expiry, "C", 110.0, 0.05, 5.0, last=(good.bid + good.ask) / 2, last_trade=AS_OF
    )
    assert isclose(quote_iv(traded, 100.0, AS_OF, 0.04, 0.0), 0.3, abs_tol=1e-3)
    stale = Quote(
        good.expiry, "C", 110.0, 0.05, 5.0, last=traded.last, last_trade=date(2025, 10, 21)
    )
    assert quote_iv(stale, 100.0, AS_OF, 0.04, 0.0) is None


def test_solve_ivs_drops_stale_quotes_priced_above_nearer_strikes() -> None:
    quotes = [_quote("C", strike) for strike in (102.0, 104.0, 106.0, 108.0, 110.0)]
    stale = Quote(quotes[0].expiry, "C", 107.0, 15.5, 16.0)
    ivs = solve_ivs([*quotes, stale], 100.0, AS_OF, 0.04, 0.0)
    assert ivs[-1] is None
    assert all(isclose(iv, 0.3, abs_tol=1e-3) for iv in ivs[:-1])


def test_term_iv_linear_in_total_variance() -> None:
    iv = term_iv([(20, 0.2), (50, 0.3)], 30)
    expected = ((0.04 * 20 + (10 / 30) * (0.09 * 50 - 0.04 * 20)) / 30) ** 0.5
    assert isclose(iv, expected)
    assert term_iv([(35, 0.25)], 30) == 0.25  # nearest within 10 days
    assert term_iv([(60, 0.25)], 30) is None


def test_summarize_flat_surface() -> None:
    expiries = (date(2026, 11, 20), date(2026, 12, 18), date(2027, 1, 15), date(2027, 2, 19))
    quotes = [
        _quote(kind, strike, expiry=expiry, volume=10 if kind == "C" else 5, open_interest=100)
        for expiry in expiries
        for strike in range(80, 121, 2)
        for kind in ("C", "P")
    ]
    ivs = solve_ivs(quotes, 100.0, AS_OF, 0.04, 0.0)
    read = summarize(
        quotes, ivs, spot=100.0, as_of=AS_OF, earnings_date=date(2026, 11, 10), rv_1y=0.25
    )
    assert isclose(read.atm_iv_30d, 0.3, abs_tol=2e-3)
    assert isclose(read.atm_iv_90d, 0.3, abs_tol=2e-3)
    assert abs(read.skew_30d) < 2e-3
    assert isclose(read.iv_rv, 1.2, abs_tol=0.01)
    assert isclose(read.pc_volume, 0.5) and isclose(read.pc_oi, 1.0)
    assert read.move_expiry == date(2026, 11, 20)
    assert 0.03 < read.expected_move < 0.08
    far = summarize(
        quotes, ivs, spot=100.0, as_of=AS_OF, earnings_date=date(2027, 1, 27), rv_1y=None
    )
    assert far.expected_move is None and far.iv_rv is None


def test_iv_rank_needs_a_year() -> None:
    assert iv_rank([0.2] * 100, 0.3) is None
    assert iv_rank([0.1, 0.2, 0.3, 0.4] * 63, 0.25) == 0.5


def test_cboe_fixture_parses_six_products() -> None:
    payload = json.loads(FIXTURE.read_text())
    stats = {row.product: row for row in stats_from_payload(AS_OF, payload)}
    assert set(stats) == {"total", "index", "etp", "equity", "vix", "spx"}
    assert stats["equity"].pc_ratio == Decimal("0.66")
    assert stats["total"].call_volume == 10250848
    del payload["EQUITY OPTIONS"]
    with pytest.raises(CboeParseError, match="EQUITY OPTIONS"):
        stats_from_payload(AS_OF, payload)


def test_underlying_uses_next_earnings_and_percent_dividend() -> None:
    def stamp(day: datetime) -> int:
        return int(day.timestamp())

    quote = {
        "regularMarketPrice": 521.91,
        "regularMarketTime": stamp(datetime(2026, 10, 30, 20, 0, tzinfo=UTC)),
        "dividendYield": 0.75,
        "earningsTimestamp": stamp(datetime(2026, 10, 28, 20, 0, tzinfo=UTC)),
        "earningsTimestampStart": stamp(datetime(2027, 1, 27, 21, 0, tzinfo=UTC)),
        "isEarningsDateEstimate": True,
    }
    underlying = underlying_from_quote("MSFT", quote)
    assert underlying.as_of == AS_OF
    assert underlying.earnings_date == date(2027, 1, 27)
    assert underlying.earnings_estimate is True
    assert underlying.dividend_yield == Decimal("0.0075")


def test_market_options_ratio_and_put_call_mean() -> None:
    from types import SimpleNamespace

    from api.options import build_market_options, build_ticker_options

    days = [date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + i) for i in range(12)]
    closes = {
        "^VIX": [(day, Decimal("20")) for day in days],
        "^VIX3M": [(day, Decimal("25")) for day in days],
        "^VIX9D": [(days[-1], Decimal("18"))],
    }
    cboe = [
        SimpleNamespace(as_of=day, product="equity", pc_ratio=Decimal(str(0.5 + i / 100)))
        for i, day in enumerate(days)
    ]
    market = build_market_options(closes, cboe)
    assert market.vix_ratio == 0.8
    assert [point.value for point in market.vix_curve] == [18.0, 20.0, 25.0]
    assert market.put_call_history[-1].equity_10d == pytest.approx(0.565)
    assert market.put_call[0].pct_1y is None  # under half a year stored
    assert build_ticker_options(None, [], []).unavailable.startswith("Not in the options scope")
