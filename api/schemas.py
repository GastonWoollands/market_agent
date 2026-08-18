from datetime import datetime

from pydantic import BaseModel


class JobStatus(BaseModel):
    job_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows_written: int
    error: str | None


class HealthResponse(BaseModel):
    ok: bool
    database: str
    database_error: str | None = None
    tape_instruments: int = 0
    watchlist_instruments: int = 0
    daily_bars: int = 0
    quotes: int = 0
    jobs: list[JobStatus] = []


class LiveQuote(BaseModel):
    ticker: str
    name: str
    role: str | None = None
    price: float | None = None
    change_pct: float | None = None
    market_state: str | None = None
    as_of: datetime | None = None


class LiveResponse(BaseModel):
    as_of: datetime | None = None
    market_state: str | None = None
    stale: bool = True
    header: list[LiveQuote] = []
    movers: list[LiveQuote] = []
