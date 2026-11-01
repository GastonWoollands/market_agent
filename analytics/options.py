"""Options read from stored chains (Northstar §9, Phase 1.12).

- IV is recomputed from the bid/ask mid with Black-Scholes and a continuous dividend
  yield, out-of-the-money side only: puts below spot, calls at or above. The price is the
  mid when bid > 0 and the spread is at most half the mid (10c floor); otherwise the last
  trade if it printed in the same session (after-hours quotes on thin ETFs widen to
  several dollars); otherwise the row has no IV. A price above that of a strike nearer
  the money is dropped (no-arbitrage monotonicity). Then any IV more than
  15 vol points and 40% off the median of its four strike neighbours (stale quotes:
  an XLE call bid at 22% of spot a year after its last trade). Yahoo's own IV on deep
  in-the-money rows is unusable (2.35 on a MSFT call struck at half of spot), so it is
  stored but never read.
- Per expiry: ATM IV interpolates in strike at spot between the nearest OTM put below and
  the nearest OTM call above. Skew = IV at 90% moneyness (puts) − IV at 110% (calls).
- Across expiries: linear in total variance (σ²·t). 30d / 90d never extrapolate; the
  nearest expiry within 10 days stands in when the target is not bracketed.
- Expected move: straddle mid at the strike nearest spot for the first stored expiry on
  or after the earnings date, ÷ spot. It covers the whole span to that expiry, so it is
  only read when earnings are within 45 days; further out it is mostly plain diffusion.

Stdlib only. Floats inside, the job casts to Decimal.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

DAYS_PER_YEAR = 365.0
MIN_DTE = 7
MONTHLIES = 4
NEAREST_DAYS = 10
IV_FLOOR = 1e-4
IV_CEILING = 5.0
BISECTIONS = 100
ATM_REACH = 0.025
EARNINGS_WINDOW_DAYS = 45
SKEW_PUT = 0.9
SKEW_CALL = 1.1
MAX_SPREAD = 0.5
MIN_SPREAD_ALLOWED = 0.10
OUTLIER_ABS = 0.15
OUTLIER_REL = 0.4
NEIGHBOURS = 2


@dataclass(frozen=True)
class Quote:
    expiry: date
    kind: str  # "C" or "P"
    strike: float
    bid: float | None
    ask: float | None
    volume: int | None = None
    open_interest: int | None = None
    last: float | None = None
    last_trade: date | None = None  # ET session of the last print


@dataclass(frozen=True)
class ExpiryRead:
    expiry: date
    dte: int
    atm_iv: float | None
    put_90: float | None
    call_110: float | None
    smile: tuple[tuple[float, float, str], ...]  # (moneyness, iv, kind), by strike


@dataclass(frozen=True)
class OptionRead:
    atm_iv_30d: float | None
    atm_iv_90d: float | None
    term_slope: float | None
    skew_30d: float | None
    iv_rv: float | None
    call_volume: int
    put_volume: int
    call_oi: int
    put_oi: int
    pc_volume: float | None
    pc_oi: float | None
    move_expiry: date | None
    expected_move: float | None
    expiries: int
    contracts: int


def monthly_expiries(
    expiries: Sequence[date], as_of: date, *, count: int = MONTHLIES, min_dte: int = MIN_DTE
) -> list[date]:
    """Third-Friday expiries (Thursday when Friday is a holiday), nearest first."""
    by_month: dict[tuple[int, int], list[date]] = {}
    for day in expiries:
        if 15 <= day.day <= 21 and day.weekday() in (3, 4):
            by_month.setdefault((day.year, day.month), []).append(day)
    picked = [max(days, key=lambda day: day.weekday()) for days in by_month.values()]
    return sorted(day for day in picked if (day - as_of).days >= min_dte)[:count]


def mid(quote: Quote) -> float | None:
    if quote.bid is None or quote.ask is None or quote.bid <= 0 or quote.ask < quote.bid:
        return None
    return (quote.bid + quote.ask) / 2


def option_price(quote: Quote, as_of: date) -> float | None:
    """Tight mid, else a same-session last trade, else None."""
    price = mid(quote)
    if price is not None and quote.ask - quote.bid <= max(MAX_SPREAD * price, MIN_SPREAD_ALLOWED):
        return price
    if quote.last and quote.last > 0 and quote.last_trade == as_of:
        return quote.last
    return None


def bs_price(
    kind: str, spot: float, strike: float, t: float, r: float, q: float, vol: float
) -> float:
    root = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r - q + vol**2 / 2) * t) / root
    d2 = d1 - root
    spot_pv = spot * math.exp(-q * t)
    strike_pv = strike * math.exp(-r * t)
    if kind == "C":
        return spot_pv * _cdf(d1) - strike_pv * _cdf(d2)
    return strike_pv * _cdf(-d2) - spot_pv * _cdf(-d1)


def implied_vol(
    kind: str, price: float, spot: float, strike: float, t: float, r: float, q: float
) -> float | None:
    """Bisection. None when the price sits outside the no-arbitrage bounds or the range."""
    if price <= 0 or spot <= 0 or strike <= 0 or t <= 0:
        return None
    spot_pv = spot * math.exp(-q * t)
    strike_pv = strike * math.exp(-r * t)
    if kind == "C":
        lower, upper = max(spot_pv - strike_pv, 0.0), spot_pv
    else:
        lower, upper = max(strike_pv - spot_pv, 0.0), strike_pv
    if not lower < price < upper:
        return None
    low, high = IV_FLOOR, IV_CEILING
    if bs_price(kind, spot, strike, t, r, q, high) < price:
        return None
    for _ in range(BISECTIONS):
        middle = (low + high) / 2
        if bs_price(kind, spot, strike, t, r, q, middle) < price:
            low = middle
        else:
            high = middle
        if high - low < 1e-7:
            break
    return (low + high) / 2


def solve_ivs(
    quotes: Sequence[Quote], spot: float, as_of: date, r: float, q: float
) -> list[float | None]:
    """`quote_iv` per row; then, within each expiry and side, prices that rise moving away
    from spot (an OTM option can never be worth more than one nearer the money) and
    strike-neighbour IV outliers → None."""
    ivs = [quote_iv(quote, spot, as_of, r, q) for quote in quotes]
    groups: dict[tuple[date, str], list[int]] = {}
    for index, (quote, iv) in enumerate(zip(quotes, ivs, strict=True)):
        if iv is not None:
            groups.setdefault((quote.expiry, quote.kind), []).append(index)
    for (expiry, kind), indices in groups.items():
        outward = sorted(indices, key=lambda index: quotes[index].strike, reverse=kind == "P")
        cap = math.inf
        for index in outward:
            price = option_price(quotes[index], as_of) or math.inf
            if price > cap:
                ivs[index] = None
            else:
                cap = price
        groups[(expiry, kind)] = [index for index in indices if ivs[index] is not None]
    out = list(ivs)
    for indices in groups.values():
        ordered = sorted(indices, key=lambda index: quotes[index].strike)
        for position, index in enumerate(ordered):
            near = (
                ordered[max(position - NEIGHBOURS, 0) : position]
                + ordered[position + 1 : position + 1 + NEIGHBOURS]
            )
            if len(near) < 2:
                continue
            centre = statistics.median(ivs[other] for other in near)
            gap = abs(ivs[index] - centre)
            if gap > OUTLIER_ABS and gap > OUTLIER_REL * centre:
                out[index] = None
    return out


def quote_iv(quote: Quote, spot: float, as_of: date, r: float, q: float) -> float | None:
    """Our IV for the out-of-the-money side; None for in-the-money rows and bad quotes."""
    if (quote.kind == "P") != (quote.strike < spot):
        return None
    price = option_price(quote, as_of)
    if price is None:
        return None
    t = (quote.expiry - as_of).days / DAYS_PER_YEAR
    return implied_vol(quote.kind, price, spot, quote.strike, t, r, q)


def expiry_read(
    expiry: date, as_of: date, spot: float, points: Sequence[tuple[str, float, float]]
) -> ExpiryRead:
    """`points` are (kind, strike, iv) for one expiry, OTM rows with an IV only."""
    puts = sorted((strike, iv) for kind, strike, iv in points if kind == "P")
    calls = sorted((strike, iv) for kind, strike, iv in points if kind == "C")
    below = puts[-1] if puts else None
    above = calls[0] if calls else None
    if below and above and above[0] > below[0]:
        weight = (spot - below[0]) / (above[0] - below[0])
        atm = below[1] + weight * (above[1] - below[1])
    else:
        near = [p for p in (below, above) if p and abs(p[0] / spot - 1) <= ATM_REACH]
        atm = near[0][1] if near else None
    smile = tuple(
        sorted(
            [(strike / spot, iv, "P") for strike, iv in puts]
            + [(strike / spot, iv, "C") for strike, iv in calls]
        )
    )
    return ExpiryRead(
        expiry=expiry,
        dte=(expiry - as_of).days,
        atm_iv=atm,
        put_90=_interp(puts, SKEW_PUT * spot),
        call_110=_interp(calls, SKEW_CALL * spot),
        smile=smile,
    )


def term_iv(points: Sequence[tuple[int, float]], target: int) -> float | None:
    """IV at `target` days, linear in total variance between the bracketing expiries."""
    ordered = sorted((dte, iv) for dte, iv in points if dte > 0)
    for (d0, v0), (d1, v1) in zip(ordered, ordered[1:], strict=False):
        if d0 <= target <= d1:
            w0, w1 = v0**2 * d0, v1**2 * d1
            weight = (target - d0) / (d1 - d0)
            variance = w0 + weight * (w1 - w0)
            return math.sqrt(variance / target) if variance > 0 else None
    near = [(abs(dte - target), iv) for dte, iv in ordered if abs(dte - target) <= NEAREST_DAYS]
    return min(near)[1] if near else None


def summarize(
    quotes: Sequence[Quote],
    ivs: Sequence[float | None],
    *,
    spot: float,
    as_of: date,
    earnings_date: date | None,
    rv_1y: float | None,
) -> OptionRead:
    """Daily read from one name's stored chain and the IVs `quote_iv` solved for it."""
    by_expiry: dict[date, list[tuple[str, float, float]]] = {}
    for quote, iv in zip(quotes, ivs, strict=True):
        by_expiry.setdefault(quote.expiry, [])
        if iv is not None:
            by_expiry[quote.expiry].append((quote.kind, quote.strike, iv))
    reads = [expiry_read(expiry, as_of, spot, rows) for expiry, rows in sorted(by_expiry.items())]
    atm = [(read.dte, read.atm_iv) for read in reads if read.atm_iv is not None]
    iv_30 = term_iv(atm, 30)
    iv_90 = term_iv(atm, 90)
    put_30 = term_iv([(r.dte, r.put_90) for r in reads if r.put_90 is not None], 30)
    call_30 = term_iv([(r.dte, r.call_110) for r in reads if r.call_110 is not None], 30)

    call_volume = sum(q.volume or 0 for q in quotes if q.kind == "C")
    put_volume = sum(q.volume or 0 for q in quotes if q.kind == "P")
    call_oi = sum(q.open_interest or 0 for q in quotes if q.kind == "C")
    put_oi = sum(q.open_interest or 0 for q in quotes if q.kind == "P")
    move_expiry, move = _expected_move(quotes, spot, as_of, earnings_date)
    return OptionRead(
        atm_iv_30d=iv_30,
        atm_iv_90d=iv_90,
        term_slope=None if iv_30 is None or iv_90 is None else iv_90 - iv_30,
        skew_30d=None if put_30 is None or call_30 is None else put_30 - call_30,
        iv_rv=None if iv_30 is None or not rv_1y else iv_30 / rv_1y,
        call_volume=call_volume,
        put_volume=put_volume,
        call_oi=call_oi,
        put_oi=put_oi,
        pc_volume=put_volume / call_volume if call_volume else None,
        pc_oi=put_oi / call_oi if call_oi else None,
        move_expiry=move_expiry,
        expected_move=move,
        expiries=len(by_expiry),
        contracts=len(quotes),
    )


def iv_rank(history: Sequence[float], today: float, *, min_sessions: int = 252) -> float | None:
    """Share of the trailing year's stored 30d IVs at or below today. None until a year exists."""
    window = list(history)[-min_sessions:]
    if len(window) < min_sessions:
        return None
    return sum(1 for value in window if value <= today) / len(window)


def _expected_move(
    quotes: Sequence[Quote], spot: float, as_of: date, earnings_date: date | None
) -> tuple[date | None, float | None]:
    if earnings_date is None or (earnings_date - as_of).days > EARNINGS_WINDOW_DAYS:
        return None, None
    after = sorted({q.expiry for q in quotes if q.expiry >= earnings_date})
    if not after:
        return None, None
    expiry = after[0]
    mids: dict[tuple[str, float], float] = {}
    for quote in quotes:
        price = mid(quote) if quote.expiry == expiry else None
        if price is not None:
            mids[(quote.kind, quote.strike)] = price
    strikes = sorted(
        {strike for kind, strike in mids if kind == "C" and ("P", strike) in mids},
        key=lambda strike: abs(strike - spot),
    )
    if not strikes:
        return expiry, None
    strike = strikes[0]
    return expiry, (mids[("C", strike)] + mids[("P", strike)]) / spot


def _interp(points: Sequence[tuple[float, float]], x: float) -> float | None:
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (x - x0) / (x1 - x0) * (y1 - y0)
    return None


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
