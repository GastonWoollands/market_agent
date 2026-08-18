import { cn } from "@/lib/cn";
import type { LiveQuote, LiveTape } from "@/lib/api";

const SESSION_LABEL: Record<string, string> = {
  REGULAR: "Regular",
  PRE: "Pre-market",
  PREPRE: "Pre-market",
  POST: "After-hours",
  POSTPOST: "After-hours",
  CLOSED: "Closed",
};

export function LiveTapeView({ tape }: { tape: LiveTape | null }) {
  if (tape == null) {
    return (
      <EmptyState message="Live API unreachable. Start uvicorn, then refresh." />
    );
  }

  const session = tape.market_state
    ? SESSION_LABEL[tape.market_state] ?? tape.market_state
    : "No session";
  const priced = tape.header.some((item) => item.price != null);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Live</h1>
        <p className="text-[13px] text-mute">
          {session}
          <span className="mx-2 text-line">·</span>
          delayed ~15 min
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

      <section className="grid gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
        {tape.header.map((item) => (
          <QuoteCell key={item.ticker} item={item} />
        ))}
      </section>

      {!priced ? (
        <p className="text-sm text-mute">
          No delayed quotes yet. Run <code className="text-white">python -m jobs.ingest_yahoo</code>{" "}
          then refresh.
        </p>
      ) : null}

      <section>
        <h2 className="mb-2 text-[11px] uppercase tracking-wide text-mute">Sector movers</h2>
        <div className="overflow-hidden rounded border border-line">
          {tape.movers.map((item, index) => (
            <MoverRow key={item.ticker} item={item} last={index === tape.movers.length - 1} />
          ))}
        </div>
      </section>
    </div>
  );
}

function QuoteCell({ item }: { item: LiveQuote }) {
  return (
    <div className="bg-panel px-3 py-3">
      <div className="truncate text-[11px] uppercase tracking-wide text-mute">{item.name}</div>
      <div className="mt-1 text-lg tabular-nums tracking-tight">{formatPrice(item.price)}</div>
      <div className={cn("mt-0.5 text-[13px] tabular-nums", changeClass(item.change_pct))}>
        {formatPct(item.change_pct)}
      </div>
    </div>
  );
}

function MoverRow({ item, last }: { item: LiveQuote; last: boolean }) {
  return (
    <div
      className={cn(
        "flex items-baseline gap-3 bg-panel px-3 py-2.5",
        last ? "" : "border-b border-line",
      )}
    >
      <div className="min-w-0 flex-1 truncate text-sm">{item.name}</div>
      <div className="w-12 shrink-0 text-right text-[12px] text-mute">{item.ticker}</div>
      <div className="w-20 shrink-0 text-right text-sm tabular-nums">{formatPrice(item.price)}</div>
      <div className={cn("w-16 shrink-0 text-right text-sm tabular-nums", changeClass(item.change_pct))}>
        {formatPct(item.change_pct)}
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">Live</h1>
      <p className="text-sm text-mute">{message}</p>
    </div>
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
