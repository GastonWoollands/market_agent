from datetime import date, datetime
from decimal import Decimal

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


class OddsPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    question: str
    implied_yes: Decimal
    liquidity: Decimal | None = None
    as_of: datetime
    raw: dict | None = None


class NewsHeadline(BaseModel):
    model_config = ConfigDict(frozen=True)

    guid: str
    title: str
    url: str
    publisher: str
    published_at: datetime
    category: str
    query: str


class CalendarEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    date: date
    title: str
    kind: str
    source: str
    ticker: str | None = None
    extra: dict | None = None


class SecTicker(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: str
    ticker: str
    name: str
    exchange: str


class MetricTtm(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: str
    as_of: date
    revenue: Decimal
    ebitda: Decimal | None = None
    fcf: Decimal | None = None
    net_debt: Decimal | None = None
    shares: Decimal | None = None
