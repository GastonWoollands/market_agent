import Link from "next/link";

import { MacroChart } from "@/components/MacroChart";
import { cn } from "@/lib/cn";
import type { LiveDrilldown, LiveMacro, LiveOdds, LiveQuote, LiveTape, LiveWatch } from "@/lib/api";

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
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
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

        <section className="grid gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-3 lg:grid-cols-3 xl:grid-cols-6">
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

        {tape.drilldown ? <Drilldown panel={tape.drilldown} /> : null}

        <section>
          <h2 className="mb-2 text-[11px] uppercase tracking-wide text-mute">Sector movers</h2>
          <div className="overflow-hidden rounded border border-line">
            {tape.movers.map((item, index) => (
              <MoverRow key={item.ticker} item={item} last={index === tape.movers.length - 1} />
            ))}
          </div>
        </section>
      </div>
      <aside className="space-y-6">
        <MacroSidebar items={tape.macro ?? []} selected={tape.drilldown?.series_id ?? "DGS10"} />
        <OddsPanel items={tape.odds ?? []} />
      </aside>
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

function MacroSidebar({ items, selected }: { items: LiveMacro[]; selected: string }) {
  const tenYear = items.find((item) => item.series_id === "DGS10");
  const hasValues = items.some((item) => item.value != null);
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-[11px] uppercase tracking-wide text-mute">Macro</h2>
        <span className="text-[11px] text-mute">
          {tenYear?.as_of ? `10Y as of ${formatDateOnly(tenYear.as_of)}` : "FRED"}
        </span>
      </div>
      <div className="overflow-hidden rounded border border-line">
        {items.map((item, index) => (
          <MacroRow
            key={item.series_id}
            item={item}
            selected={item.series_id === selected}
            last={index === items.length - 1}
          />
        ))}
      </div>
      {!hasValues ? (
        <p className="mt-2 text-[12px] leading-5 text-mute">
          No FRED prints yet. Set <code className="text-white">FRED_API_KEY</code> and run{" "}
          <code className="text-white">python -m jobs.ingest_fred</code>.
        </p>
      ) : null}
    </div>
  );
}

function MacroRow({
  item,
  selected,
  last,
}: {
  item: LiveMacro;
  selected: boolean;
  last: boolean;
}) {
  const period = item.frequency === "monthly" ? "1M" : "1D";
  return (
    <Link
      href={`/?lever=${encodeURIComponent(item.series_id)}`}
      className={cn(
        "flex items-baseline gap-2 bg-panel px-3 py-2 hover:bg-white/5",
        last ? "" : "border-b border-line",
        selected ? "bg-white/5" : "",
      )}
    >
      <div className="min-w-0 flex-1 truncate text-[13px]">{item.name}</div>
      <div className="shrink-0 text-right text-[13px] tabular-nums">
        {formatMacroValue(item.unit, item.value)}
      </div>
      <div
        className={cn("w-14 shrink-0 text-right text-[12px] tabular-nums", changeClass(item.change))}
        title={`${period} change in native FRED units`}
      >
        {formatMacroChange(item.change)}
      </div>
    </Link>
  );
}

function Drilldown({ panel }: { panel: LiveDrilldown }) {
  const y1 = panel.deltas.y1;
  const positive = (y1 ?? panel.deltas.d1 ?? 0) >= 0;
  return (
    <section className="overflow-hidden rounded border border-line bg-panel">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-mute">{panel.series_id}</div>
          <h2 className="text-lg font-semibold tracking-tight">{panel.name}</h2>
        </div>
        <div className="text-right">
          <div className="text-xl tabular-nums">{formatMacroValue(panel.unit, panel.value)}</div>
          <div className="text-[12px] text-mute">
            {panel.as_of ? `as of ${formatDateOnly(panel.as_of)}` : "no print"}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-px border-b border-line bg-line">
        <DeltaCell label="1D" unit={panel.unit} value={panel.deltas.d1} />
        <DeltaCell label="1W" unit={panel.unit} value={panel.deltas.w1} />
        <DeltaCell label="1M" unit={panel.unit} value={panel.deltas.m1} />
        <DeltaCell label="1Y" unit={panel.unit} value={panel.deltas.y1} />
      </div>
      <MacroChart points={panel.points} unit={panel.unit} positive={positive} />
      {panel.insight ? (
        <p className="border-t border-line px-4 py-3 text-[13px] leading-6 text-mute">{panel.insight}</p>
      ) : null}
      {panel.watch.length > 0 ? (
        <div className="flex flex-wrap gap-2 border-t border-line px-4 py-3">
          {panel.watch.map((item) => (
            <WatchChip key={item.ticker} item={item} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function DeltaCell({ label, unit, value }: { label: string; unit: string; value: number | null }) {
  return (
    <div className="bg-panel px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-mute">{label}</div>
      <div className={cn("mt-0.5 text-sm tabular-nums", changeClass(value))} title={unit}>
        {formatMacroChange(value)}
      </div>
    </div>
  );
}

function WatchChip({ item }: { item: LiveWatch }) {
  return (
    <span className="rounded border border-line px-2 py-1 text-[12px] tabular-nums">
      {item.ticker}{" "}
      <span className={changeClass(item.change_pct)}>{formatPct(item.change_pct)}</span>
    </span>
  );
}

function OddsPanel({ items }: { items: LiveOdds[] }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-[11px] uppercase tracking-wide text-mute">Market-implied</h2>
        <span className="text-[11px] text-mute">not a forecast</span>
      </div>
      {items.length === 0 ? (
        <p className="text-[12px] leading-5 text-mute">
          No odds yet. Run <code className="text-white">python -m jobs.ingest_polymarket</code>.
        </p>
      ) : (
        <div className="overflow-hidden rounded border border-line">
          {items.map((item, index) => (
            <OddsRow key={item.slug} item={item} last={index === items.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function OddsRow({ item, last }: { item: LiveOdds; last: boolean }) {
  const extras = item.outcomes.filter((outcome) => outcome.implied_yes !== item.implied_yes).slice(0, 3);
  return (
    <div className={cn("bg-panel px-3 py-2.5", last ? "" : "border-b border-line")}>
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0 truncate text-[13px]">{item.label}</div>
        <div className="shrink-0 text-right text-[13px] tabular-nums">
          {formatImplied(item.implied_yes)}
        </div>
      </div>
      <div className="mt-0.5 truncate text-[11px] text-mute" title={item.question}>
        {item.thin ? "thin book · " : null}
        {shortQuestion(item.question)}
      </div>
      {extras.length > 0 ? (
        <div className="mt-1 space-y-0.5">
          {extras.map((outcome) => (
            <div key={outcome.label} className="flex justify-between gap-2 text-[11px] text-mute">
              <span className="min-w-0 truncate">{shortQuestion(outcome.label)}</span>
              <span className="tabular-nums">{formatImplied(outcome.implied_yes)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatImplied(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function shortQuestion(value: string): string {
  const trimmed = value.replace(/^Will (the |there be )?/i, "").replace(/\?$/, "");
  return trimmed.length > 48 ? `${trimmed.slice(0, 45)}…` : trimmed;
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

function formatDateOnly(value: string): string {
  const parts = value.split("-").map(Number);
  if (parts.length < 3 || parts.some((part) => Number.isNaN(part))) {
    return value;
  }
  const [year, month, day] = parts;
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function formatMacroValue(unit: string, value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  if (unit === "percent") {
    return `${value.toFixed(2)}%`;
  }
  if (unit === "usd_per_barrel") {
    return value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatMacroChange(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  const abs = Math.abs(value).toFixed(2);
  if (value > 0) {
    return `+${abs}`;
  }
  if (value < 0) {
    return `-${abs}`;
  }
  return abs;
}
