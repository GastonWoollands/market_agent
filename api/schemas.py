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
    news_items: int = 0
    event_items: int = 0
    evidence_packs: int = 0
    outlook_reports: int = 0
    valuation_instruments: int = 0
    metric_ttm: int = 0
    valuation_daily: int = 0
    opportunity_scores: int = 0
    opportunity_memos: int = 0
    intraday_bars: int = 0
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


class DynamicsOverlay(BaseModel):
    ticker: str
    name: str
    points: list[DynamicsPoint] = Field(default_factory=list)


class DynamicsCorr(BaseModel):
    window: int
    tickers: list[str]
    matrix: list[list[float | None]]


class DynamicsLagBar(BaseModel):
    lag: int
    corr: float | None = None


class DynamicsLeadLag(BaseModel):
    left: str
    right: str
    peak_lag: int | None = None
    note: str
    bars: list[DynamicsLagBar] = Field(default_factory=list)


class DynamicsResponse(BaseModel):
    as_of: date | None = None
    stale: bool = True
    benchmark: str = "SPY"
    members: list[DynamicsMember] = Field(default_factory=list)
    overlay: list[DynamicsOverlay] = Field(default_factory=list)
    corr: DynamicsCorr | None = None
    lead_lag: DynamicsLeadLag | None = None


class OutlookSource(BaseModel):
    vendor: str
    job_name: str
    as_of: datetime | None = None
    status: str | None = None
    rows: int = 0
    error: str | None = None


class OutlookNews(BaseModel):
    title: str
    publisher: str
    published_at: datetime
    category: str
    url: str


class OutlookEvent(BaseModel):
    date: date
    title: str
    kind: str
    ticker: str | None = None
    source: str


class OutlookResponse(BaseModel):
    as_of: date | None = None
    stale: bool = True
    pack_id: int | None = None
    pack_hash: str | None = None
    brief: str | None = None
    brief_status: str | None = None
    brief_model: str | None = None
    news: list[OutlookNews] = Field(default_factory=list)
    events: list[OutlookEvent] = Field(default_factory=list)
    sources: list[OutlookSource] = Field(default_factory=list)


class ValuationMember(BaseModel):
    ticker: str
    name: str
    exchange: str | None = None
    industry: str | None = None
    cik: str | None = None
    as_of: date | None = None
    revenue: float | None = None
    ebitda: float | None = None
    fcf: float | None = None
    net_debt: float | None = None
    ev: float | None = None
    ev_ebitda: float | None = None
    pctile_5y: float | None = None
    ebitda_growth_1y: float | None = None
    multiple_change_1y: float | None = None
    comparable: bool = False


class ValuationResponse(BaseModel):
    as_of: date | None = None
    stale: bool = True
    min_revenue: float = 1_000_000_000
    comparable_n: int = 0
    comparable_m: int = 0
    count: int = 0
    q: str = ""
    industry: str = ""
    sort: str = "pctile"
    min_rev: float | None = None
    industries: list[str] = Field(default_factory=list)
    members: list[ValuationMember] = Field(default_factory=list)


class OpportunityMemo(BaseModel):
    why_scored: str
    what_10q_changed: str
    invalidation: str
    caveats: str
    model: str
    status: str


class OpportunityMember(BaseModel):
    ticker: str
    name: str
    rank: int
    total: float
    cheap: float
    quality: float
    change: float
    setup: float
    insider: float
    risk: float
    trap: bool
    pctile_5y: float | None = None
    ev_ebitda: float | None = None
    ebitda_growth_1y: float | None = None
    fcf_margin: float | None = None
    ret_3m: float | None = None
    memo: OpportunityMemo | None = None


class OpportunityResponse(BaseModel):
    as_of: date | None = None
    stale: bool = True
    count: int = 0
    sort: str = "rank"
    members: list[OpportunityMember] = Field(default_factory=list)


class WatchlistSparkPoint(BaseModel):
    date: date
    value: float


class WatchlistPoint(BaseModel):
    ts: datetime
    value: float


class WatchlistMember(BaseModel):
    ticker: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    market_state: str | None = None
    as_of: datetime | None = None
    tv_symbol: str
    sparkline: list[WatchlistSparkPoint] = Field(default_factory=list)
    intraday: list[WatchlistPoint] = Field(default_factory=list)


class WatchlistAdd(BaseModel):
    ticker: str


class WatchlistResponse(BaseModel):
    as_of: datetime | None = None
    stale: bool = True
    selected: str | None = None
    members: list[WatchlistMember] = Field(default_factory=list)


class SearchHit(BaseModel):
    ticker: str
    name: str
    exchange: str | None = None
    asset_class: str


class SearchResponse(BaseModel):
    q: str
    hits: list[SearchHit] = Field(default_factory=list)
