"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { TradingViewChart } from "@/components/TradingViewChart";
import { BROWSER_API, type WatchlistMember, type WatchlistTape } from "@/lib/api";
import { cn } from "@/lib/cn";

export function WatchlistView({
  tape,
  selected,
}: {
  tape: WatchlistTape | null;
  selected: string;
}) {
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (tape == null) {
    return (
      <p className="text-sm text-mute">Watchlist API unreachable. Start uvicorn, then refresh.</p>
    );
  }

  const active =
    tape.members.find((item) => item.ticker === (selected || tape.selected)) ?? tape.members[0];

  async function addTicker(event: FormEvent) {
    event.preventDefault();
    const ticker = draft.trim();
    if (!ticker) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`${BROWSER_API}/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? `Add failed (${response.status})`);
      }
      setDraft("");
      router.replace(`/watchlist?ticker=${encodeURIComponent(ticker.toUpperCase())}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add failed");
    } finally {
      setPending(false);
    }
  }

  async function removeTicker(ticker: string) {
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`${BROWSER_API}/watchlist/${encodeURIComponent(ticker)}`, {
        method: "DELETE",
      });
      if (!response.ok && response.status !== 204) {
        throw new Error(`Remove failed (${response.status})`);
      }
      router.replace("/watchlist");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Watchlist</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            Quotes and sparklines come from Postgres. The chart is the official TradingView widget,
            not a scraped feed. Extended-hours 5m is tape + watchlist only.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.members.length} names
          {tape.as_of ? (
            <>
              <span className="mx-2 text-line">·</span>
              as of {formatAsOf(tape.as_of)}
            </>
          ) : null}
          {tape.stale ? (
            <>
              <span className="mx-2 text-line">·</span>
              stale
            </>
          ) : null}
        </p>
      </div>

      <form onSubmit={addTicker} className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] uppercase tracking-wide text-mute">
          Add ticker
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="NVDA"
            className="mt-1 block h-8 w-40 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="h-8 rounded border border-line bg-panel px-3 text-[13px] text-white disabled:text-mute"
        >
          Add
        </button>
        {error ? <p className="text-[13px] text-down">{error}</p> : null}
      </form>

      {tape.members.length === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.seed_tape</code>, then{" "}
          <code className="text-white">python -m jobs.ingest_yahoo --universe watchlist</code>.
        </p>
      ) : (
        <section className="grid gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {tape.members.map((item) => (
            <QuoteCard
              key={item.ticker}
              item={item}
              active={active?.ticker === item.ticker}
              onSelect={() => {
                router.replace(`/watchlist?ticker=${encodeURIComponent(item.ticker)}`);
              }}
              onRemove={() => void removeTicker(item.ticker)}
              disabled={pending}
            />
          ))}
        </section>
      )}

      {active ? (
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-mute">{active.name}</div>
              <div className="mt-1 flex items-baseline gap-3">
                <span className="text-2xl tabular-nums tracking-tight">
                  {formatPrice(active.price)}
                </span>
                <span className={cn("text-sm tabular-nums", changeClass(active.change_pct))}>
                  {formatPct(active.change_pct)}
                </span>
                <span className="text-[13px] text-mute">{active.ticker}</span>
              </div>
            </div>
            <p className="text-[13px] text-mute">
              DB quote
              {active.market_state ? (
                <>
                  <span className="mx-2 text-line">·</span>
                  {active.market_state.toLowerCase()}
                </>
              ) : null}
              {active.intraday.length > 0 ? (
                <>
                  <span className="mx-2 text-line">·</span>
                  {active.intraday.length} 5m bars
                </>
              ) : (
                <>
                  <span className="mx-2 text-line">·</span>
                  no 5m yet — <code className="text-white">python -m jobs.ingest_intraday</code>
                </>
              )}
            </p>
          </div>
          <TradingViewChart symbol={active.tv_symbol} />
        </section>
      ) : null}
    </div>
  );
}

function QuoteCard({
  item,
  active,
  onSelect,
  onRemove,
  disabled,
}: {
  item: WatchlistMember;
  active: boolean;
  onSelect: () => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  const spark = item.sparkline.map((point) => point.value);
  const sparkDelta = spark.length >= 2 ? spark[spark.length - 1] - spark[0] : 0;
  const sparkUp = sparkDelta === 0 ? null : sparkDelta > 0;
  return (
    <div className={cn("bg-panel px-3 py-3", active ? "ring-1 ring-inset ring-white/20" : "")}>
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-[11px] uppercase tracking-wide text-mute">{item.name}</div>
            <div className="mt-1 text-lg tabular-nums tracking-tight">{formatPrice(item.price)}</div>
            <div className={cn("mt-0.5 text-[13px] tabular-nums", changeClass(item.change_pct))}>
              {formatPct(item.change_pct)}
            </div>
          </div>
          <Sparkline values={spark} up={sparkUp} />
        </div>
      </button>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[12px] text-mute">{item.ticker}</span>
        <button
          type="button"
          onClick={onRemove}
          disabled={disabled}
          className="text-[12px] text-mute hover:text-white disabled:text-mute"
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function Sparkline({ values, up }: { values: number[]; up: boolean | null }) {
  if (values.length < 2) {
    return <div className="h-7 w-[72px]" />;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 72;
  const height = 28;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x},${y}`;
    })
    .join(" ");
  const stroke = up == null ? "#8a8a8a" : up ? "#3dd68c" : "#ef5b5b";
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <polyline fill="none" stroke={stroke} strokeWidth="1.25" points={points} />
    </svg>
  );
}

function formatPrice(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatPct(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  const abs = Math.abs(value).toFixed(2);
  if (value > 0) {
    return `+${abs}%`;
  }
  if (value < 0) {
    return `-${abs}%`;
  }
  return `${abs}%`;
}

function changeClass(value: number | null): string {
  if (value == null || value === 0) {
    return "text-mute";
  }
  return value > 0 ? "text-up" : "text-down";
}

function formatAsOf(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}
