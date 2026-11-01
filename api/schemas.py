from datetime import date, datetime
from typing import Literal

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
    metric_fy: int = 0
    valuation_daily: int = 0
    opportunity_scores: int = 0
    opportunity_memos: int = 0
    quant_score: int = 0
    intraday_bars: int = 0
    jobs: list[JobStatus] = []


class LiveQuote(BaseModel):
    ticker: str
    name: str
    role: str | None = None
    price: float | None = None
    change_pct: float | None = None
    change_bp: float | None = None
    change_kind: str | None = None
    gap_pct: float | None = None
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
    spine: bool = False


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
    slot: str
    slug: str
    label: str
    category: str
    question: str
    implied_yes: float | None = None
    liquidity: float | None = None
    thin: bool = False
    as_of: datetime | None = None
    outcomes: list[LiveOddsOutcome] = Field(default_factory=list)


class LiveEvent(BaseModel):
    date: date
    title: str
    kind: str
    ticker: str | None = None
    source: str


class LiveBrief(BaseModel):
    headline: str | None = None
    live_md: str | None = None
    expect: str | None = None
    as_of: date | None = None
    status: str | None = None


class LiveOutlier(BaseModel):
    id: str
    window: str = "1d"
    change: float | None = None
    z: float | None = None


class LiveCoMove(BaseModel):
    ids: list[str] = Field(default_factory=list)
    window: str = "1d"
    changes: dict[str, float] = Field(default_factory=dict)
    hint: str | None = None


class LiveRegime(BaseModel):
    """Macro regime read (growth / inflation / policy / volatility) with confidence 0..1."""

    as_of: date | None = None
    growth: str | None = None
    inflation: str | None = None
    policy: str | None = None
    volatility: str | None = None
    growth_confidence: float | None = None
    inflation_confidence: float | None = None
    policy_confidence: float | None = None
    volatility_confidence: float | None = None


class LiveLiquidity(BaseModel):
    """Net liquidity = Fed balance sheet − (reverse repo + Treasury general account)."""

    net_liquidity_bn: float | None = None
    wow_change_bn: float | None = None
    fed_bs_bn: float | None = None
    rrp_bn: float | None = None
    tga_bn: float | None = None


class LiveAnomaly(BaseModel):
    type: str
    description: str
    severity: float


class LiveResponse(BaseModel):
    as_of: datetime | None = None
    market_state: str | None = None
    stale: bool = True
    header: list[LiveQuote] = []
    intl: list[LiveQuote] = Field(default_factory=list)
    yields: list[LiveQuote] = Field(default_factory=list)
    movers: list[LiveQuote] = []
    macro: list[LiveMacro] = []
    drilldown: LiveDrilldown | None = None
    risk_on: LiveRiskOn | None = None
    regime: LiveRegime | None = None
    liquidity: LiveLiquidity | None = None
    anomalies: list[LiveAnomaly] = Field(default_factory=list)
    odds: list[LiveOdds] = Field(default_factory=list)
    events: list[LiveEvent] = Field(default_factory=list)
    brief: LiveBrief | None = None
    outliers: list[LiveOutlier] = Field(default_factory=list)
    co_moves: list[LiveCoMove] = Field(default_factory=list)
    watchlist_outliers: list[LiveQuote] = Field(default_factory=list)


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
    summary: str | None = None


class OutlookEvent(BaseModel):
    date: date
    title: str
    kind: str
    ticker: str | None = None
    source: str


class OutlookMacro(BaseModel):
    series_id: str
    name: str | None = None
    unit: str | None = None
    category: str | None = None
    region: str | None = None
    frequency: str | None = None
    pack_view: str | None = None
    as_of: str | None = None
    lag_days: int | None = None
    stale: bool = False
    value: float | None = None
    yoy_pct: float | None = None
    mom_pct: float | None = None
    d1_bp: float | None = None
    w1_bp: float | None = None
    m1_bp: float | None = None
    mom_change: float | None = None
    print_change: float | None = None
    change_label: str | None = None
    spine: bool = False
    d1: float | None = None
    w1: float | None = None
    m1: float | None = None


class OutlookOddsOutcome(BaseModel):
    label: str
    implied_yes: float


class OutlookOdds(BaseModel):
    slot: str | None = None
    slug: str
    label: str | None = None
    category: str | None = None
    implied_yes: float | None = None
    as_of: str | None = None
    outcomes: list[OutlookOddsOutcome] = Field(default_factory=list)
    top_outcome: str | None = None
    top_implied_yes: float | None = None


class OutlookTension(BaseModel):
    left: str
    right: str
    note: str


class OutlookWatch(BaseModel):
    date: str | None = None
    title: str | None = None
    kind: str | None = None
    last_print: str | None = None
    why: str | None = None
    role: str | None = None


class OutlookOutlier(BaseModel):
    id: str
    window: str = "1d"
    change: float | None = None
    z: float | None = None


class OutlookCoMove(BaseModel):
    ids: list[str] = Field(default_factory=list)
    window: str = "1d"
    changes: dict[str, float] = Field(default_factory=dict)
    hint: str | None = None


class OutlookPolicyComms(BaseModel):
    event: str | None = None
    kind: str | None = None
    speaker: str | None = None
    stance: str | None = None
    tensions: list[OutlookTension] = Field(default_factory=list)


class OutlookPolicyItem(BaseModel):
    published_at: str | None = None
    kind: str
    speaker: str | None = None
    title: str
    url: str | None = None
    excerpt: str | None = None


class OutlookJudgment(BaseModel):
    takeaways: list[str] = Field(default_factory=list)
    tensions: list[OutlookTension] = Field(default_factory=list)
    regime: dict[str, str | None] = Field(default_factory=dict)
    watch: list[OutlookWatch] = Field(default_factory=list)
    invalidation: str | None = None
    odds_read: str | None = None
    abstract: str | None = None
    outliers: list[OutlookOutlier] = Field(default_factory=list)
    co_moves: list[OutlookCoMove] = Field(default_factory=list)
    policy_comms: OutlookPolicyComms | None = None


class OutlookWatchScenario(BaseModel):
    """Structured scenario for a watch item with branching outcomes."""

    catalyst: str
    date: str | None = None
    time: str | None = None
    outcome_bullish: str
    outcome_bearish: str
    threshold: str | None = None


class OutlookCalendarItem(BaseModel):
    """Structured calendar entry with consensus/prior."""

    date: str
    time: str | None = None
    event: str
    consensus: str | None = None
    prior: str | None = None
    source: str | None = None


class OutlookResponse(BaseModel):
    as_of: date | None = None
    stale: bool = True
    pack_id: int | None = None
    pack_hash: str | None = None
    brief: str | None = None
    brief_status: str | None = None
    brief_model: str | None = None

    # Core fields
    headline: str | None = None
    tldr: str | None = None
    what_happened: str | None = None
    current_positioning: str | None = None
    drivers: str | None = None

    # Scenario planning
    watch_today: list[OutlookWatchScenario] = Field(default_factory=list)
    invalidation: str | None = None

    # Deep sections
    macro_deep: str | None = None
    market_deep: str | None = None
    policy_deep: str | None = None
    geopolitical_deep: str | None = None

    # Calendar
    calendar: list[OutlookCalendarItem] = Field(default_factory=list)

    # Legacy fields (kept for backward compat)
    abstract: str | None = None
    conclusions: list[str] = Field(default_factory=list)
    expect: str | None = None
    live_md: str | None = None
    macro_md: str | None = None
    market_md: str | None = None
    near_term_md: str | None = None

    # Pack data
    facts: dict[str, float | None] = Field(default_factory=dict)
    judgment: OutlookJudgment | None = None
    macro_snapshot: list[OutlookMacro] = Field(default_factory=list)
    odds: list[OutlookOdds] = Field(default_factory=list)
    news: list[OutlookNews] = Field(default_factory=list)
    events: list[OutlookEvent] = Field(default_factory=list)
    events_later: list[OutlookEvent] = Field(default_factory=list)
    policy_items: list[OutlookPolicyItem] = Field(default_factory=list)
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
    fcf_yield: float | None = None
    nd_ebitda: float | None = None
    accrual: bool | None = None
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
    fcf_yield: float | None = None
    nd_ebitda: float | None = None
    accrual: bool | None = None
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


class TickerIdentity(BaseModel):
    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    cik: str | None = None
    universes: list[str] = Field(default_factory=list)
    tv_symbol: str
    sector_etf: str | None = None


class TickerPrice(BaseModel):
    as_of: date
    close: float
    change_1d: float | None = None


class TickerDesk(BaseModel):
    """Named desk metrics. `ev_basis` says whether EV is the stored daily or read-time."""

    ttm_as_of: date | None = None
    valuation_as_of: date | None = None
    ev_basis: str | None = None
    market_cap: float | None = None
    ev: float | None = None
    ev_ebitda: float | None = None
    pctile_5y: float | None = None
    comparable: bool = False
    sample_size: int | None = None
    fcf_yield: float | None = None
    nd_ebitda: float | None = None
    ebitda_growth_1y: float | None = None
    revenue_growth_1y: float | None = None
    interest_coverage: float | None = None
    share_change_1y: float | None = None
    financing_gap: float | None = None
    accrual: bool | None = None
    rank: int | None = None
    ranked: int | None = None
    trap: bool | None = None


class TickerTtmRow(BaseModel):
    as_of: date
    revenue: float | None = None
    ebitda: float | None = None
    ebit: float | None = None
    cfo: float | None = None
    capex: float | None = None
    fcf: float | None = None
    net_debt: float | None = None
    interest_expense: float | None = None
    shares: float | None = None


class TickerFyRow(BaseModel):
    as_of: date
    fiscal_year: int
    revenue: float | None = None
    net_income: float | None = None
    cfo: float | None = None
    ebit: float | None = None
    gross_profit: float | None = None
    long_term_debt: float | None = None
    equity: float | None = None
    shares: float | None = None


class TickerTechnicals(BaseModel):
    as_of: date
    sma_20: float | None = None
    sma_50: float | None = None
    sma_100: float | None = None
    sma_200: float | None = None
    vs_sma_20: float | None = None
    vs_sma_50: float | None = None
    vs_sma_100: float | None = None
    vs_sma_200: float | None = None
    rsi_14: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    vs_high_52w: float | None = None
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_1y: float | None = None
    rel_spy_3m: float | None = None
    rel_spy_1y: float | None = None
    rel_sector_3m: float | None = None
    rel_sector_1y: float | None = None


class TickerRisk(BaseModel):
    as_of: date
    source: str
    sessions: int
    vol_3m: float | None = None
    vol_1y: float | None = None
    downside_vol_1y: float | None = None
    beta_spy: float | None = None
    beta_qqq: float | None = None
    corr_spy: float | None = None
    max_drawdown_1y: float | None = None
    drawdown: float | None = None


class TickerEvent(BaseModel):
    date: date
    title: str
    kind: str


class TickerNews(BaseModel):
    published_at: datetime
    title: str
    url: str
    publisher: str


class PeerRow(BaseModel):
    ticker: str
    name: str | None = None
    is_self: bool = False
    market_cap: float | None = None
    ev_ebitda: float | None = None
    pctile_5y: float | None = None
    fcf_yield: float | None = None
    nd_ebitda: float | None = None
    ebitda_growth_1y: float | None = None
    ret_1y: float | None = None
    vol_1y: float | None = None
    rank: int | None = None


class PeerPoint(BaseModel):
    ticker: str
    ev_ebitda: float
    ebitda_growth_1y: float
    market_cap: float | None = None
    is_self: bool = False


class TickerPeers(BaseModel):
    """Same-sector valuation members nearest by market cap, plus sector medians."""

    sector: str
    sector_size: int
    basis: Literal["nearest_cap", "largest_cap"] = "nearest_cap"
    rows: list[PeerRow] = Field(default_factory=list)
    medians: PeerRow
    scatter: list[PeerPoint] = Field(default_factory=list)


class CreditAnchorRow(BaseModel):
    bucket: str
    median_dd: float
    names: int
    oas_bp: float | None = None


class AgencyRating(BaseModel):
    rating: str
    bucket: str
    agency: str
    as_of: str | None = None
    source: str | None = None


class TickerCredit(BaseModel):
    """Equity-implied credit bucket. The bp is the bucket's market OAS, not this name's spread."""

    source: Literal["stored", "read_time"] | None = None
    unavailable: str | None = None
    as_of: date | None = None
    statement_as_of: date | None = None
    market_cap: float | None = None
    default_point: float | None = None
    vol_equity: float | None = None
    asset_value: float | None = None
    vol_asset: float | None = None
    risk_free: float | None = None
    dd: float | None = None
    bucket: str | None = None
    position: Literal["above", "within", "below"] | None = None
    bucket_oas_bp: float | None = None
    calibration_version: str | None = None
    agency: AgencyRating | None = None
    anchors: list[CreditAnchorRow] = Field(default_factory=list)


class OptionTermPoint(BaseModel):
    expiry: date
    dte: int
    atm_iv: float


class OptionSmilePoint(BaseModel):
    moneyness: float
    iv: float
    kind: Literal["C", "P"]


class TickerOptions(BaseModel):
    """Options read from the stored chain. `unavailable` explains an empty block."""

    as_of: date | None = None
    spot: float | None = None
    atm_iv_30d: float | None = None
    atm_iv_90d: float | None = None
    term_slope: float | None = None
    skew_30d: float | None = None
    rv_1y: float | None = None
    iv_rv: float | None = None
    iv_rank: float | None = None
    iv_sessions: int = 0
    pc_volume: float | None = None
    pc_oi: float | None = None
    call_volume: int | None = None
    put_volume: int | None = None
    earnings_date: date | None = None
    earnings_estimate: bool | None = None
    move_expiry: date | None = None
    expected_move: float | None = None
    term: list[OptionTermPoint] = Field(default_factory=list)
    smile_expiry: date | None = None
    smile: list[OptionSmilePoint] = Field(default_factory=list)
    unavailable: str | None = None


class TickerResponse(BaseModel):
    stale: bool = True
    identity: TickerIdentity | None = None
    price: TickerPrice | None = None
    desk: TickerDesk | None = None
    ttm: list[TickerTtmRow] = Field(default_factory=list)
    fy: list[TickerFyRow] = Field(default_factory=list)
    technicals: TickerTechnicals | None = None
    risk: TickerRisk | None = None
    events: list[TickerEvent] = Field(default_factory=list)
    news: list[TickerNews] = Field(default_factory=list)
    peers: TickerPeers | None = None
    credit: TickerCredit | None = None
    options: TickerOptions | None = None
    hint: str | None = None


class CompareRow(BaseModel):
    identity: TickerIdentity
    price: TickerPrice | None = None
    desk: TickerDesk | None = None
    technicals: TickerTechnicals | None = None
    risk: TickerRisk | None = None


class CompareResponse(BaseModel):
    as_of: date | None = None
    stale: bool = True
    benchmark: str = "SPY"
    tickers: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    rows: list[CompareRow] = Field(default_factory=list)
    corr: DynamicsCorr | None = None
    overlay: list[DynamicsOverlay] = Field(default_factory=list)


class CreditBucket(BaseModel):
    rating: str
    grade: Literal["IG", "HY"]
    oas_bp: float | None = None
    oas_1m_bp: float | None = None
    oas_1y_bp: float | None = None
    yield_pct: float | None = None
    yield_1y_pct: float | None = None


class CreditCurveResponse(BaseModel):
    """ICE BofA OAS and effective yield by rating bucket (FRED), plus conditions gauges."""

    stale: bool = True
    as_of: date | None = None
    buckets: list[CreditBucket] = Field(default_factory=list)
    baa_10y_bp: float | None = None
    nfci: float | None = None
    nfci_as_of: date | None = None
    stlfsi: float | None = None
    stlfsi_as_of: date | None = None


class VixTermPoint(BaseModel):
    ticker: str
    label: str
    days: int
    value: float | None = None


class VolIndexRow(BaseModel):
    ticker: str
    label: str
    value: float | None = None
    change_1d: float | None = None
    pct_1y: float | None = None


class VixRatioPoint(BaseModel):
    date: date
    ratio: float


class PutCallPoint(BaseModel):
    date: date
    equity: float | None = None
    index: float | None = None
    total: float | None = None
    spx: float | None = None
    equity_10d: float | None = None


class PutCallLatest(BaseModel):
    product: str
    label: str
    ratio: float | None = None
    pct_1y: float | None = None


class MarketOptionsResponse(BaseModel):
    as_of: date | None = None
    vix_curve: list[VixTermPoint] = Field(default_factory=list)
    vix_ratio: float | None = None
    vix_ratio_history: list[VixRatioPoint] = Field(default_factory=list)
    indices: list[VolIndexRow] = Field(default_factory=list)
    put_call_as_of: date | None = None
    put_call: list[PutCallLatest] = Field(default_factory=list)
    put_call_history: list[PutCallPoint] = Field(default_factory=list)
