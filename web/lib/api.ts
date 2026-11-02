export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Same-origin prefix (Next rewrite → uvicorn). Use in client components only. */
export const BROWSER_API = "/backend";

export type JobStatus = {
  job_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  rows_written: number;
  error: string | null;
};

export type Health = {
  ok: boolean;
  database: string;
  database_error?: string | null;
  tape_instruments: number;
  watchlist_instruments: number;
  daily_bars?: number;
  quotes?: number;
  macro_observations?: number;
  odds_snapshots?: number;
  rrg_points?: number;
  return_stats?: number;
  news_items?: number;
  event_items?: number;
  evidence_packs?: number;
  outlook_reports?: number;
  valuation_instruments?: number;
  metric_ttm?: number;
  metric_fy?: number;
  valuation_daily?: number;
  opportunity_scores?: number;
  opportunity_memos?: number;
  quant_score?: number;
  intraday_bars?: number;
  jobs: JobStatus[];
};

export type LiveQuote = {
  ticker: string;
  name: string;
  role: string | null;
  price: number | null;
  change_pct: number | null;
  change_bp?: number | null;
  change_kind?: string | null;
  gap_pct?: number | null;
  market_state: string | null;
  as_of: string | null;
};

export type LiveMacro = {
  series_id: string;
  name: string;
  unit: string;
  category: string | null;
  frequency: string;
  value: number | null;
  change: number | null;
  as_of: string | null;
  spine?: boolean;
};

export type LiveDeltas = {
  d1: number | null;
  w1: number | null;
  m1: number | null;
  y1: number | null;
};

export type LivePoint = {
  date: string;
  value: number;
};

export type LiveWatch = {
  ticker: string;
  name: string;
  change_pct: number | null;
};

export type LiveDrilldown = {
  series_id: string;
  name: string;
  unit: string;
  insight: string | null;
  as_of: string | null;
  value: number | null;
  deltas: LiveDeltas;
  points: LivePoint[];
  watch: LiveWatch[];
};

export type LiveRiskOn = {
  score: number | null;
  as_of: string | null;
  stale: boolean;
  factors: Record<string, number | null>;
};

export type LiveOddsOutcome = {
  label: string;
  implied_yes: number;
};

export type LiveOdds = {
  slot: string;
  slug: string;
  label: string;
  category: string;
  question: string;
  implied_yes: number | null;
  liquidity: number | null;
  thin: boolean;
  as_of: string | null;
  outcomes: LiveOddsOutcome[];
};

export type LiveEvent = {
  date: string;
  title: string;
  kind: string;
  ticker: string | null;
  source: string;
};

export type LiveBrief = {
  headline: string | null;
  live_md: string | null;
  expect: string | null;
  as_of: string | null;
  status: string | null;
};

export type LiveOutlier = {
  id: string;
  window: string;
  change: number | null;
  z: number | null;
};

export type LiveCoMove = {
  ids: string[];
  window: string;
  changes: Record<string, number>;
  hint: string | null;
};

export type LiveRegime = {
  as_of: string | null;
  growth: string | null;
  inflation: string | null;
  policy: string | null;
  volatility: string | null;
  growth_confidence: number | null;
  inflation_confidence: number | null;
  policy_confidence: number | null;
  volatility_confidence: number | null;
};

export type LiveLiquidity = {
  net_liquidity_bn: number | null;
  wow_change_bn: number | null;
  fed_bs_bn: number | null;
  rrp_bn: number | null;
  tga_bn: number | null;
};

export type LiveAnomaly = {
  type: string;
  description: string;
  severity: number;
};

export type LiveTape = {
  as_of: string | null;
  market_state: string | null;
  stale: boolean;
  header: LiveQuote[];
  intl?: LiveQuote[];
  yields?: LiveQuote[];
  movers: LiveQuote[];
  macro: LiveMacro[];
  drilldown: LiveDrilldown | null;
  risk_on: LiveRiskOn | null;
  regime?: LiveRegime | null;
  liquidity?: LiveLiquidity | null;
  anomalies?: LiveAnomaly[];
  odds: LiveOdds[];
  events?: LiveEvent[];
  brief?: LiveBrief | null;
  outliers?: LiveOutlier[];
  co_moves?: LiveCoMove[];
  watchlist_outliers?: LiveQuote[];
};

export async function fetchHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}

export async function fetchLive(lever = "DGS10"): Promise<LiveTape | null> {
  try {
    const query = new URLSearchParams({ lever });
    const response = await fetch(`${API_URL}/live?${query.toString()}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as LiveTape;
  } catch {
    return null;
  }
}

export type DynamicsTrailPoint = {
  as_of: string;
  rs_ratio: number;
  rs_momentum: number;
};

export type DynamicsPoint = {
  date: string;
  value: number;
};

export type DynamicsMember = {
  ticker: string;
  name: string;
  role: string | null;
  sector: string | null;
  quadrant: string;
  rs_ratio: number;
  rs_momentum: number;
  trail: DynamicsTrailPoint[];
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  ret_1y: number | null;
  indexed: DynamicsPoint[];
};

export type DynamicsTape = {
  as_of: string | null;
  stale: boolean;
  benchmark: string;
  members: DynamicsMember[];
  overlay: DynamicsOverlay[];
  corr: DynamicsCorr | null;
  lead_lag: DynamicsLeadLag | null;
};

export type DynamicsOverlay = {
  ticker: string;
  name: string;
  points: DynamicsPoint[];
};

export type DynamicsCorr = {
  window: number;
  tickers: string[];
  matrix: (number | null)[][];
};

export type DynamicsLagBar = {
  lag: number;
  corr: number | null;
};

export type DynamicsLeadLag = {
  left: string;
  right: string;
  peak_lag: number | null;
  note: string;
  bars: DynamicsLagBar[];
};

export async function fetchDynamics(opts?: {
  asOf?: string;
  lead?: string;
  lag?: string;
}): Promise<DynamicsTape | null> {
  try {
    const query = new URLSearchParams();
    if (opts?.asOf) {
      query.set("as_of", opts.asOf);
    }
    if (opts?.lead) {
      query.set("lead", opts.lead);
    }
    if (opts?.lag) {
      query.set("lag", opts.lag);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const response = await fetch(`${API_URL}/dynamics${suffix}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as DynamicsTape;
  } catch {
    return null;
  }
}

export type OutlookSource = {
  vendor: string;
  job_name: string;
  as_of: string | null;
  status: string | null;
  rows: number;
  error: string | null;
};

export type OutlookNews = {
  title: string;
  publisher: string;
  published_at: string;
  category: string;
  url: string;
  summary?: string | null;
};

export type OutlookEvent = {
  date: string;
  title: string;
  kind: string;
  ticker: string | null;
  source: string;
};

export type OutlookMacro = {
  series_id: string;
  name: string | null;
  unit: string | null;
  category: string | null;
  region: string | null;
  frequency: string | null;
  pack_view: string | null;
  as_of: string | null;
  lag_days: number | null;
  stale: boolean;
  value: number | null;
  yoy_pct: number | null;
  mom_pct: number | null;
  d1_bp: number | null;
  w1_bp: number | null;
  m1_bp: number | null;
  mom_change: number | null;
  print_change: number | null;
  change_label: string | null;
  spine: boolean;
  d1: number | null;
  w1: number | null;
  m1: number | null;
};

export type OutlookOddsOutcome = {
  label: string;
  implied_yes: number;
};

export type OutlookOdds = {
  slot?: string | null;
  slug: string;
  label: string | null;
  category: string | null;
  implied_yes: number | null;
  as_of: string | null;
  outcomes: OutlookOddsOutcome[];
  top_outcome: string | null;
  top_implied_yes: number | null;
};

export type OutlookTension = {
  left: string;
  right: string;
  note: string;
};

export type OutlookWatch = {
  date: string | null;
  title: string | null;
  kind: string | null;
  last_print: string | null;
  why: string | null;
  role?: string | null;
};

export type OutlookPolicyComms = {
  event: string | null;
  kind: string | null;
  speaker: string | null;
  stance: string | null;
  tensions: OutlookTension[];
};

export type OutlookPolicyItem = {
  published_at: string | null;
  kind: string;
  speaker: string | null;
  title: string;
  url: string | null;
  excerpt: string | null;
};

export type OutlookJudgment = {
  takeaways: string[];
  tensions: OutlookTension[];
  regime: Record<string, string | null>;
  watch: OutlookWatch[];
  invalidation: string | null;
  odds_read: string | null;
  abstract: string | null;
  policy_comms?: OutlookPolicyComms | null;
};

export type OutlookWatchScenario = {
  catalyst: string;
  date: string | null;
  time: string | null;
  outcome_bullish: string;
  outcome_bearish: string;
  threshold: string | null;
};

export type OutlookCalendarItem = {
  date: string;
  time: string | null;
  event: string;
  consensus: string | null;
  prior: string | null;
  source: string | null;
};

export type OutlookTape = {
  as_of: string | null;
  stale: boolean;
  pack_id: number | null;
  pack_hash: string | null;
  brief: string | null;
  brief_status: string | null;
  brief_model: string | null;
  // Core fields
  headline: string | null;
  tldr: string | null;
  what_happened: string | null;
  current_positioning: string | null;
  drivers: string | null;
  // Scenario planning
  watch_today: OutlookWatchScenario[];
  invalidation: string | null;
  // Deep sections
  macro_deep: string | null;
  market_deep: string | null;
  policy_deep: string | null;
  geopolitical_deep: string | null;
  // Calendar
  calendar: OutlookCalendarItem[];
  // Legacy fields
  abstract: string | null;
  conclusions: string[];
  expect: string | null;
  live_md?: string | null;
  macro_md: string | null;
  market_md: string | null;
  near_term_md: string | null;
  facts: Record<string, number | null>;
  judgment: OutlookJudgment | null;
  macro_snapshot: OutlookMacro[];
  odds: OutlookOdds[];
  news: OutlookNews[];
  events: OutlookEvent[];
  events_later: OutlookEvent[];
  policy_items?: OutlookPolicyItem[];
  sources: OutlookSource[];
};

export async function fetchOutlook(asOf?: string): Promise<OutlookTape | null> {
  try {
    const query = asOf ? `?${new URLSearchParams({ as_of: asOf }).toString()}` : "";
    const response = await fetch(`${API_URL}/outlook${query}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as OutlookTape;
  } catch {
    return null;
  }
}

export type ValuationMember = {
  ticker: string;
  name: string;
  exchange: string | null;
  industry: string | null;
  cik: string | null;
  as_of: string | null;
  revenue: number | null;
  ebitda: number | null;
  fcf: number | null;
  net_debt: number | null;
  ev: number | null;
  ev_ebitda: number | null;
  pctile_5y: number | null;
  ebitda_growth_1y: number | null;
  multiple_change_1y: number | null;
  fcf_yield: number | null;
  nd_ebitda: number | null;
  accrual: boolean | null;
  comparable: boolean;
};

export type ValuationTape = {
  as_of: string | null;
  stale: boolean;
  min_revenue: number;
  comparable_n: number;
  comparable_m: number;
  count: number;
  q: string;
  industry: string;
  sort: string;
  min_rev: number | null;
  industries: string[];
  members: ValuationMember[];
};

export async function fetchValuation(query?: {
  q?: string;
  industry?: string;
  sort?: string;
  minRev?: string;
}): Promise<ValuationTape | null> {
  try {
    const params = new URLSearchParams();
    if (query?.q) {
      params.set("q", query.q);
    }
    if (query?.industry) {
      params.set("industry", query.industry);
    }
    if (query?.sort) {
      params.set("sort", query.sort);
    }
    if (query?.minRev) {
      params.set("min_rev", query.minRev);
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`${API_URL}/valuation${suffix}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as ValuationTape;
  } catch {
    return null;
  }
}

export type OpportunityMemo = {
  why_scored: string;
  what_10q_changed: string;
  invalidation: string;
  caveats: string;
  model: string;
  status: string;
};

export type OpportunityMember = {
  ticker: string;
  name: string;
  rank: number;
  total: number;
  cheap: number;
  quality: number;
  change: number;
  setup: number;
  insider: number;
  risk: number;
  trap: boolean;
  pctile_5y: number | null;
  ev_ebitda: number | null;
  ebitda_growth_1y: number | null;
  fcf_margin: number | null;
  fcf_yield: number | null;
  nd_ebitda: number | null;
  accrual: boolean | null;
  ret_3m: number | null;
  memo: OpportunityMemo | null;
};

export type OpportunityTape = {
  as_of: string | null;
  stale: boolean;
  count: number;
  sort: string;
  members: OpportunityMember[];
};

export async function fetchOpportunities(query?: {
  sort?: string;
  asOf?: string;
}): Promise<OpportunityTape | null> {
  try {
    const params = new URLSearchParams();
    if (query?.sort) {
      params.set("sort", query.sort);
    }
    if (query?.asOf) {
      params.set("as_of", query.asOf);
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`${API_URL}/opportunities${suffix}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    const tape = (await response.json()) as OpportunityTape;
    return { ...tape, members: tape.members ?? [] };
  } catch {
    return null;
  }
}

export type WatchlistSparkPoint = {
  date: string;
  value: number;
};

export type WatchlistPoint = {
  ts: string;
  value: number;
};

export type WatchlistMember = {
  ticker: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  market_state: string | null;
  as_of: string | null;
  tv_symbol: string;
  sparkline: WatchlistSparkPoint[];
  intraday: WatchlistPoint[];
};

export type WatchlistTape = {
  as_of: string | null;
  stale: boolean;
  selected: string | null;
  members: WatchlistMember[];
};

export async function fetchWatchlist(ticker?: string): Promise<WatchlistTape | null> {
  try {
    const query = ticker ? `?${new URLSearchParams({ ticker }).toString()}` : "";
    const response = await fetch(`${API_URL}/watchlist${query}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as WatchlistTape;
  } catch {
    return null;
  }
}

export type TickerIdentity = {
  ticker: string;
  name: string;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  cik: string | null;
  universes: string[];
  tv_symbol: string;
  sector_etf: string | null;
};

export type TickerPrice = {
  as_of: string;
  close: number;
  change_1d: number | null;
};

export type TickerDesk = {
  ttm_as_of: string | null;
  valuation_as_of: string | null;
  ev_basis: "valuation_daily" | "read_time" | null;
  market_cap: number | null;
  ev: number | null;
  ev_ebitda: number | null;
  pctile_5y: number | null;
  comparable: boolean;
  sample_size: number | null;
  fcf_yield: number | null;
  nd_ebitda: number | null;
  ebitda_growth_1y: number | null;
  revenue_growth_1y: number | null;
  interest_coverage: number | null;
  share_change_1y: number | null;
  financing_gap: number | null;
  accrual: boolean | null;
  rank: number | null;
  ranked: number | null;
  trap: boolean | null;
};

export type TickerTtmRow = {
  as_of: string;
  revenue: number | null;
  ebitda: number | null;
  ebit: number | null;
  cfo: number | null;
  capex: number | null;
  fcf: number | null;
  net_debt: number | null;
  interest_expense: number | null;
  shares: number | null;
};

export type TickerFyRow = {
  as_of: string;
  fiscal_year: number;
  revenue: number | null;
  net_income: number | null;
  cfo: number | null;
  ebit: number | null;
  gross_profit: number | null;
  long_term_debt: number | null;
  equity: number | null;
  shares: number | null;
};

export type TickerTechnicals = {
  as_of: string;
  sma_20: number | null;
  sma_50: number | null;
  sma_100: number | null;
  sma_200: number | null;
  vs_sma_20: number | null;
  vs_sma_50: number | null;
  vs_sma_100: number | null;
  vs_sma_200: number | null;
  rsi_14: number | null;
  high_52w: number | null;
  low_52w: number | null;
  vs_high_52w: number | null;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  ret_6m: number | null;
  ret_1y: number | null;
  rel_spy_3m: number | null;
  rel_spy_1y: number | null;
  rel_sector_3m: number | null;
  rel_sector_1y: number | null;
};

export type TickerRisk = {
  as_of: string;
  source: "risk_stats" | "read_time";
  sessions: number;
  vol_3m: number | null;
  vol_1y: number | null;
  downside_vol_1y: number | null;
  beta_spy: number | null;
  beta_qqq: number | null;
  corr_spy: number | null;
  max_drawdown_1y: number | null;
  drawdown: number | null;
};

export type TickerEvent = { date: string; title: string; kind: string };

export type TickerNews = {
  published_at: string;
  title: string;
  url: string;
  publisher: string;
};

export type PeerRow = {
  ticker: string;
  name: string | null;
  is_self: boolean;
  market_cap: number | null;
  ev_ebitda: number | null;
  pctile_5y: number | null;
  fcf_yield: number | null;
  nd_ebitda: number | null;
  ebitda_growth_1y: number | null;
  ret_1y: number | null;
  vol_1y: number | null;
  rank: number | null;
};

export type PeerPoint = {
  ticker: string;
  ev_ebitda: number;
  ebitda_growth_1y: number;
  market_cap: number | null;
  is_self: boolean;
};

export type TickerPeers = {
  sector: string;
  sector_size: number;
  basis: "nearest_cap" | "largest_cap";
  rows: PeerRow[];
  medians: PeerRow;
  scatter: PeerPoint[];
};

export type CreditBucket = {
  rating: string;
  grade: "IG" | "HY";
  oas_bp: number | null;
  oas_1m_bp: number | null;
  oas_1y_bp: number | null;
  yield_pct: number | null;
  yield_1y_pct: number | null;
};

export type CreditCurve = {
  stale: boolean;
  as_of: string | null;
  buckets: CreditBucket[];
  baa_10y_bp: number | null;
  nfci: number | null;
  nfci_as_of: string | null;
  stlfsi: number | null;
  stlfsi_as_of: string | null;
};

export type CreditAnchorRow = {
  bucket: string;
  median_dd: number;
  names: number;
  oas_bp: number | null;
};

export type AgencyRating = {
  rating: string;
  bucket: string;
  agency: string;
  as_of: string | null;
  source: string | null;
};

export type TickerCredit = {
  source: "stored" | "read_time" | null;
  unavailable: string | null;
  as_of: string | null;
  statement_as_of: string | null;
  market_cap: number | null;
  default_point: number | null;
  vol_equity: number | null;
  asset_value: number | null;
  vol_asset: number | null;
  risk_free: number | null;
  dd: number | null;
  bucket: string | null;
  position: "above" | "within" | "below" | null;
  bucket_oas_bp: number | null;
  calibration_version: string | null;
  agency: AgencyRating | null;
  anchors: CreditAnchorRow[];
};

export type OptionTermPoint = { expiry: string; dte: number; atm_iv: number };
export type OptionSmilePoint = { moneyness: number; iv: number; kind: "C" | "P" };

export type TickerOptions = {
  as_of: string | null;
  spot: number | null;
  atm_iv_30d: number | null;
  atm_iv_90d: number | null;
  term_slope: number | null;
  skew_30d: number | null;
  rv_1y: number | null;
  iv_rv: number | null;
  iv_rank: number | null;
  iv_sessions: number;
  pc_volume: number | null;
  pc_oi: number | null;
  call_volume: number | null;
  put_volume: number | null;
  earnings_date: string | null;
  earnings_estimate: boolean | null;
  move_expiry: string | null;
  expected_move: number | null;
  term: OptionTermPoint[];
  smile_expiry: string | null;
  smile: OptionSmilePoint[];
  unavailable: string | null;
};

export type MarketOptions = {
  as_of: string | null;
  vix_curve: { ticker: string; label: string; days: number; value: number | null }[];
  vix_ratio: number | null;
  vix_ratio_history: { date: string; ratio: number }[];
  indices: {
    ticker: string;
    label: string;
    value: number | null;
    change_1d: number | null;
    pct_1y: number | null;
  }[];
  put_call_as_of: string | null;
  put_call: { product: string; label: string; ratio: number | null; pct_1y: number | null }[];
  put_call_history: {
    date: string;
    equity: number | null;
    index: number | null;
    total: number | null;
    spx: number | null;
    equity_10d: number | null;
  }[];
};

export type TickerTape = {
  stale: boolean;
  identity: TickerIdentity | null;
  price: TickerPrice | null;
  desk: TickerDesk | null;
  ttm: TickerTtmRow[];
  fy: TickerFyRow[];
  technicals: TickerTechnicals | null;
  risk: TickerRisk | null;
  events: TickerEvent[];
  news: TickerNews[];
  peers: TickerPeers | null;
  credit: TickerCredit | null;
  options: TickerOptions | null;
  hint: string | null;
};

export type CompareRow = {
  identity: TickerIdentity;
  price: TickerPrice | null;
  desk: TickerDesk | null;
  technicals: TickerTechnicals | null;
  risk: TickerRisk | null;
};

export type CompareTape = {
  as_of: string | null;
  stale: boolean;
  benchmark: string;
  tickers: string[];
  missing: string[];
  rows: CompareRow[];
  corr: DynamicsCorr | null;
  overlay: DynamicsOverlay[];
};

export type Fetched<T> = { ok: true; data: T } | { ok: false; status: number | null };

export async function fetchTicker(ticker: string): Promise<Fetched<TickerTape>> {
  return fetchTyped<TickerTape>(`/ticker/${encodeURIComponent(ticker.toUpperCase())}`);
}

export async function fetchCreditCurve(): Promise<Fetched<CreditCurve>> {
  return fetchTyped<CreditCurve>("/credit/curve");
}

export async function fetchMarketOptions(): Promise<Fetched<MarketOptions>> {
  return fetchTyped<MarketOptions>("/options/market");
}

export async function fetchCompare(tickers: string[]): Promise<Fetched<CompareTape>> {
  const params = new URLSearchParams({ tickers: tickers.join(",") });
  return fetchTyped<CompareTape>(`/compare?${params.toString()}`);
}

async function fetchTyped<T>(path: string): Promise<Fetched<T>> {
  try {
    const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return { ok: false, status: response.status };
    }
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return { ok: false, status: null };
  }
}
