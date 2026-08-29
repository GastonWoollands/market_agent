import Link from "next/link";

import { StaleBadge } from "@/components/StaleBadge";
import { MacroChart } from "@/components/MacroChart";
import { cn } from "@/lib/cn";
import type {
  LiveBrief,
  LiveCoMove,
  LiveDrilldown,
  LiveEvent,
  LiveMacro,
  LiveOdds,
  LiveOutlier,
  LiveQuote,
  LiveRiskOn,
  LiveTape,
  LiveWatch,
} from "@/lib/api";

const SESSION_LABEL: Record<string, string> = {
  REGULAR: "Regular",
  PRE: "Pre-market",
  PREPRE: "Pre-market",
  POST: "After-hours",
  POSTPOST: "After-hours",
  CLOSED: "Closed",
};

const CHANGE_KIND_LABEL: Record<string, string> = {
  gap: "Gap %",
  session: "Session %",
  after_hours: "After-hours %",
  close: "Close %",
};

const FACTOR_LABEL: Record<string, string> = {
  inv_vix: "−VIX",
  hyg_lqd: "HY/IG",
  rsp_spy: "RSP/SPY",
  curve: "2s10s",
  cyc_def: "Cyc/Def",
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
  const changeKind = tape.header.find((item) => item.change_kind)?.change_kind;
  const priced = tape.header.some((item) => item.price != null);
  const today = todayStamp(tape);
  const printedToday = (tape.macro ?? []).some((item) => item.as_of === today);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">Live</h1>
          <p className="text-[13px] text-mute">
            {session}
            {changeKind ? (
              <>
                <span className="mx-2 text-line">·</span>
                {CHANGE_KIND_LABEL[changeKind] ?? changeKind}
              </>
            ) : null}
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
                <StaleBadge stale />
              </>
            ) : null}
          </p>
        </div>

        <TodayStrip events={tape.events ?? []} odds={tape.odds ?? []} brief={tape.brief ?? null} />

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

        <RiskOnFactors riskOn={tape.risk_on} />
        <DriverBoard outliers={tape.outliers ?? []} coMoves={tape.co_moves ?? []} />
        <BriefSlice brief={tape.brief ?? null} />

        {tape.drilldown ? <Drilldown panel={tape.drilldown} /> : null}

        <section>
          <h2 className="mb-2 text-[11px] uppercase tracking-wide text-mute">Sector movers</h2>
          <div className="overflow-hidden rounded border border-line">
            {tape.movers.map((item, index) => (
              <MoverRow key={item.ticker} item={item} last={index === tape.movers.length - 1} />
            ))}
          </div>
        </section>

        <WatchlistOutliers items={tape.watchlist_outliers ?? []} />
      </div>
      <aside className="space-y-6">
        <MacroSidebar
          items={tape.macro ?? []}
          selected={tape.drilldown?.series_id ?? "DGS10"}
          today={printedToday ? today : null}
        />
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

function TodayStrip({
  events,
  odds,
  brief,
}: {
  events: LiveEvent[];
  odds: LiveOdds[];
  brief: LiveBrief | null;
}) {
  const topOdds = odds[0];
  const outcome = topOdds?.outcomes[0];
  return (
    <section className="overflow-hidden rounded border border-line">
      <div className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        Today
      </div>
      {events.length === 0 && !brief?.headline && !topOdds ? (
        <p className="px-3 py-3 text-[13px] text-mute">No stored events or brief yet.</p>
      ) : (
        <div className="space-y-2 px-3 py-3">
          {events.slice(0, 4).map((item) => (
            <div key={`${item.date}-${item.title}`} className="flex items-baseline gap-3 text-[13px]">
              <span className="w-14 shrink-0 tabular-nums text-mute">{item.date.slice(5)}</span>
              <span className="min-w-0 flex-1 truncate">{item.title}</span>
              {item.ticker ? <span className="text-mute">{item.ticker}</span> : null}
            </div>
          ))}
          {topOdds ? (
            <p className="text-[13px] text-mute">
              {topOdds.label}
              {outcome ? ` · ${shortQuestion(outcome.label)} ${formatImplied(outcome.implied_yes)}` : null}
              {!outcome && topOdds.implied_yes != null ? ` · ${formatImplied(topOdds.implied_yes)}` : null}
            </p>
          ) : null}
          {brief?.headline ? (
            <p className="text-[13px]">
              <Link href="/outlook" className="text-white hover:underline">
                {brief.headline}
              </Link>
              {brief.expect ? <span className="text-mute"> — {brief.expect}</span> : null}
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}

function RiskOnFactors({ riskOn }: { riskOn: LiveRiskOn | null }) {
  const factors = riskOn?.factors ?? {};
  const names = Object.keys(factors);
  if (names.length === 0) {
    return null;
  }
  return (
    <section className="overflow-hidden rounded border border-line">
      <div className="flex items-baseline justify-between gap-2 border-b border-line px-3 py-2">
        <h2 className="text-[11px] uppercase tracking-wide text-mute">Risk-On factors</h2>
        <span className="text-[12px] tabular-nums text-mute">
          {riskOn?.score == null ? "—" : riskOn.score > 0 ? `+${riskOn.score.toFixed(2)}` : riskOn.score.toFixed(2)}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-5">
        {names.map((name) => {
          const value = factors[name];
          return (
            <div key={name} className="bg-panel px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-mute">
                {FACTOR_LABEL[name] ?? name}
              </div>
              <div className={cn("mt-0.5 text-sm tabular-nums", changeClass(value ?? null))}>
                {value == null ? "—" : value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DriverBoard({ outliers, coMoves }: { outliers: LiveOutlier[]; coMoves: LiveCoMove[] }) {
  if (outliers.length === 0 && coMoves.length === 0) {
    return null;
  }
  return (
    <section className="space-y-2">
      <h2 className="text-[11px] uppercase tracking-wide text-mute">Outliers</h2>
      <div className="flex flex-wrap gap-2">
        {outliers.map((item) => (
          <span
            key={item.id}
            className="rounded border border-line px-2 py-1 text-[12px] tabular-nums"
            title={item.z == null ? undefined : `z ${item.z}`}
          >
            {item.id}{" "}
            <span className={changeClass(item.change)}>{formatDriverChange(item.change)}</span>
          </span>
        ))}
      </div>
      {coMoves.map((item) => (
        <p key={item.ids.join("-")} className="text-[12px] text-mute">
          {item.ids.join(" · ")}
          {Object.entries(item.changes)
            .map(([id, value]) => ` ${id} ${formatDriverChange(value)}`)
            .join("")}
        </p>
      ))}
    </section>
  );
}

function BriefSlice({ brief }: { brief: LiveBrief | null }) {
  if (brief?.live_md) {
    return (
      <section className="rounded border border-line bg-panel px-3 py-3">
        <p className="text-[11px] uppercase tracking-wide text-mute">Outlook</p>
        <p className="mt-2 text-sm leading-6">{brief.live_md}</p>
        <Link href="/outlook" className="mt-2 inline-block text-[12px] text-mute hover:text-white">
          Full Outlook
        </Link>
      </section>
    );
  }
  return (
    <p className="text-[13px] text-mute">
      Outlook unavailable. Run <code className="text-white">python -m jobs.generate_outlook</code> after{" "}
      <code className="text-white">jobs.build_pack</code>.
    </p>
  );
}

function WatchlistOutliers({ items }: { items: LiveQuote[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section>
      <h2 className="mb-2 text-[11px] uppercase tracking-wide text-mute">Watchlist outliers</h2>
      <div className="overflow-hidden rounded border border-line">
        {items.map((item, index) => (
          <Link
            key={item.ticker}
            href={`/watchlist?ticker=${encodeURIComponent(item.ticker)}`}
            className={cn(
              "flex items-baseline gap-3 bg-panel px-3 py-2.5 hover:bg-white/5",
              index === items.length - 1 ? "" : "border-b border-line",
            )}
          >
            <div className="min-w-0 flex-1 truncate text-sm">{item.name}</div>
            <div className="w-12 shrink-0 text-right text-[12px] text-mute">{item.ticker}</div>
            <div className={cn("w-16 shrink-0 text-right text-sm tabular-nums", changeClass(item.change_pct))}>
              {formatPct(item.change_pct)}
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function MacroSidebar({
  items,
  selected,
  today,
}: {
  items: LiveMacro[];
  selected: string;
  today: string | null;
}) {
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
            printedToday={today != null && item.as_of === today}
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
  printedToday,
  last,
}: {
  item: LiveMacro;
  selected: boolean;
  printedToday: boolean;
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
        printedToday ? "text-white" : "",
      )}
    >
      <div className="min-w-0 flex-1 truncate text-[13px]">
        {item.name}
        {printedToday ? <span className="ml-2 text-[11px] uppercase tracking-wide text-mute">today</span> : null}
      </div>
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

function todayStamp(tape: LiveTape): string | null {
  if (tape.as_of) {
    return tape.as_of.slice(0, 10);
  }
  const event = tape.events?.[0]?.date;
  return event ?? null;
}

function formatDriverChange(value: number | null): string {
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
