from datetime import date, datetime

from pydantic import BaseModel, Field


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
    macro_observations: int = 0
    odds_snapshots: int = 0
    rrg_points: int = 0
    return_stats: int = 0
    jobs: list[JobStatus] = []


class LiveQuote(BaseModel):
    ticker: str
    name: str
    role: str | None = None
    price: float | None = None
    change_pct: float | None = None
    market_state: str | None = None
    as_of: datetime | None = None


class LiveMacro(BaseModel):
    series_id: str
    name: str
    unit: str
    category: str | None = None
    frequency: str = "daily"
    value: float | None = None
    change: float | None = None
    as_of: date | None = None


class LiveDeltas(BaseModel):
    d1: float | None = None
    w1: float | None = None
    m1: float | None = None
    y1: float | None = None


class LivePoint(BaseModel):
    date: date
    value: float


class LiveWatch(BaseModel):
    ticker: str
    name: str
    change_pct: float | None = None


class LiveDrilldown(BaseModel):
    series_id: str
    name: str
    unit: str
    insight: str | None = None
    as_of: date | None = None
    value: float | None = None
    deltas: LiveDeltas = Field(default_factory=LiveDeltas)
    points: list[LivePoint] = Field(default_factory=list)
    watch: list[LiveWatch] = Field(default_factory=list)


class LiveRiskOn(BaseModel):
    score: float | None = None
    as_of: date | None = None
    stale: bool = True
    factors: dict[str, float | None] = Field(default_factory=dict)


class LiveOddsOutcome(BaseModel):
    label: str
    implied_yes: float


class LiveOdds(BaseModel):
    slug: str
    label: str
    category: str
    question: str
    implied_yes: float | None = None
    liquidity: float | None = None
    thin: bool = False
    as_of: datetime | None = None
    outcomes: list[LiveOddsOutcome] = Field(default_factory=list)


class LiveResponse(BaseModel):
    as_of: datetime | None = None
    market_state: str | None = None
    stale: bool = True
    header: list[LiveQuote] = []
    movers: list[LiveQuote] = []
    macro: list[LiveMacro] = []
    drilldown: LiveDrilldown | None = None
    risk_on: LiveRiskOn | None = None
    odds: list[LiveOdds] = Field(default_factory=list)


class DynamicsTrailPoint(BaseModel):
    as_of: date
    rs_ratio: float
    rs_momentum: float


class DynamicsPoint(BaseModel):
    date: date
    value: float


class DynamicsMember(BaseModel):
    ticker: str
    name: str
    role: str | None = None
    sector: str | None = None
    quadrant: str
    rs_ratio: float
    rs_momentum: float
    trail: list[DynamicsTrailPoint] = Field(default_factory=list)
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_1y: float | None = None
    indexed: list[DynamicsPoint] = Field(default_factory=list)


class DynamicsResponse(BaseModel):
    as_of: date | None = None
    stale: bool = True
    benchmark: str = "SPY"
    members: list[DynamicsMember] = Field(default_factory=list)
