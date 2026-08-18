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

export type LiveTape = {
  as_of: string | null;
  market_state: string | null;
  stale: boolean;
  header: LiveQuote[];
  movers: LiveQuote[];
  macro: LiveMacro[];
};

export async function fetchHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}

export async function fetchLive(): Promise<LiveTape | null> {
  try {
    const response = await fetch(`${API_URL}/live`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as LiveTape;
  } catch {
    return null;
  }
}
