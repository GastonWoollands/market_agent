from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DailyBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    yahoo_symbol: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adj_close: Decimal
    volume: int = 0


class IntradayBar(BaseModel):
    """5m (and similar) bars. Do not reuse DailyBar — that type collapses to a session date."""

    model_config = ConfigDict(frozen=True)

    yahoo_symbol: str
    ts: datetime
    interval: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0


class QuoteSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    yahoo_symbol: str
    price: Decimal
    change_pct: Decimal | None = None
    volume: int | None = None
    market_state: str | None = None
    as_of: datetime


class MacroPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    series_id: str
    date: date
    value: Decimal


class CboeProductStat(BaseModel):
    """One Cboe product's day: put/call ratio, volume and open interest (Cboe exchange only)."""

    model_config = ConfigDict(frozen=True)

    as_of: date
    product: str
    pc_ratio: Decimal | None = None
    call_volume: int
    put_volume: int
    call_oi: int
    put_oi: int


class OptionQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    expiry: date
    kind: Literal["C", "P"]
    strike: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    volume: int | None = None
    open_interest: int | None = None
    vendor_iv: Decimal | None = None
    last_trade_at: datetime | None = None


class OptionUnderlying(BaseModel):
    """Underlying quote that ships with the chain: spot, its time, dividend yield, earnings."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: date
    spot: Decimal
    quote_at: datetime
    dividend_yield: Decimal | None = None
    earnings_date: date | None = None
    earnings_estimate: bool | None = None


class OddsPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    question: str
    implied_yes: Decimal
    liquidity: Decimal | None = None
    as_of: datetime
    raw: dict | None = None
    slot: str = ""


class NewsHeadline(BaseModel):
    model_config = ConfigDict(frozen=True)

    guid: str
    title: str
    url: str
    publisher: str
    published_at: datetime
    category: str
    query: str
    summary: str | None = None


class CalendarEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    date: date
    title: str
    kind: str
    source: str
    ticker: str | None = None
    extra: dict | None = None


class PolicyDoc(BaseModel):
    model_config = ConfigDict(frozen=True)

    guid: str
    published_at: datetime
    title: str
    url: str
    kind: str
    speaker: str | None = None
    excerpt: str | None = None
    source: str = "fed_rss"


class SecTicker(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: str
    ticker: str
    name: str
    exchange: str


class SecProfile(BaseModel):
    """Issuer classification from the SEC submissions endpoint."""

    model_config = ConfigDict(frozen=True)

    cik: str
    sic: int | None = None
    sic_description: str | None = None


class MetricTtm(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: str
    as_of: date
    revenue: Decimal
    ebitda: Decimal | None = None
    fcf: Decimal | None = None
    cfo: Decimal | None = None
    capex: Decimal | None = None
    ebit: Decimal | None = None
    interest_expense: Decimal | None = None
    net_debt: Decimal | None = None
    shares: Decimal | None = None
    # Balance-sheet instants on `as_of`, for the credit default point.
    current_liabilities: Decimal | None = None
    total_liabilities: Decimal | None = None
    deferred_revenue_current: Decimal | None = None


class MetricFy(BaseModel):
    """One fiscal-year snapshot from companyfacts. Not a fact warehouse."""

    model_config = ConfigDict(frozen=True)

    cik: str
    as_of: date
    fiscal_year: int
    revenue: Decimal | None = None
    net_income: Decimal | None = None
    cfo: Decimal | None = None
    gross_profit: Decimal | None = None
    ebit: Decimal | None = None
    total_assets: Decimal | None = None
    current_assets: Decimal | None = None
    current_liabilities: Decimal | None = None
    long_term_debt: Decimal | None = None
    total_liabilities: Decimal | None = None
    retained_earnings: Decimal | None = None
    equity: Decimal | None = None
    shares: Decimal | None = None
