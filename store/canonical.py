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

