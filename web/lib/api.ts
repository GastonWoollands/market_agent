export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  jobs: JobStatus[];
};

export type LiveQuote = {
  ticker: string;
  name: string;
  role: string | null;
  price: number | null;
  change_pct: number | null;
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

export type LiveTape = {
  as_of: string | null;
  market_state: string | null;
  stale: boolean;
  header: LiveQuote[];
  movers: LiveQuote[];
  macro: LiveMacro[];
  drilldown: LiveDrilldown | null;
  risk_on: LiveRiskOn | null;
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
