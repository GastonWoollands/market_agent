import Link from "next/link";

import { RelativeOverlay } from "@/components/RelativeOverlay";
import { RrgScatter } from "@/components/RrgScatter";
import { cn } from "@/lib/cn";
import type { DynamicsCorr, DynamicsLeadLag, DynamicsMember, DynamicsTape } from "@/lib/api";

const QUADRANTS = [
  { id: "leading", label: "Leading" },
  { id: "weakening", label: "Weakening" },
  { id: "lagging", label: "Lagging" },
  { id: "improving", label: "Improving" },
] as const;

const QUADRANT_DOT: Record<string, string> = {
  leading: "bg-up",
  weakening: "bg-[#d4a017]",
  lagging: "bg-down",
  improving: "bg-[#6cb6ff]",
};

export function DynamicsView({ tape, asOf }: { tape: DynamicsTape | null; asOf?: string }) {
  if (tape == null) {
    return <p className="text-sm text-mute">Dynamics API unreachable. Start uvicorn, then refresh.</p>;
  }

  const grouped = Object.fromEntries(
    QUADRANTS.map((quadrant) => [
      quadrant.id,
      tape.members.filter((item) => item.quadrant === quadrant.id),
    ]),
  ) as Record<(typeof QUADRANTS)[number]["id"], DynamicsMember[]>;
  const sectors = tape.members
    .filter((item) => item.role === "sector")
    .slice()
    .sort((a, b) => (b.ret_3m ?? -Infinity) - (a.ret_3m ?? -Infinity));
  const pairTickers = Array.from(
    new Set([...tape.members.map((item) => item.ticker), ...(tape.corr?.tickers ?? [])]),
  ).sort();

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dynamics</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            JdK RS-Ratio / RS-Momentum vs {tape.benchmark} from stored daily bars. Relative overlay,
            63-session correlation, and lead-lag use the same closes. Credit and Polymarket are not
            on this page.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.as_of ? <>as of {tape.as_of}</> : "no rows"}
          {tape.stale ? (
            <>
              <span className="mx-2 text-line">·</span>
              stale
            </>
          ) : null}
        </p>
      </div>

      {tape.members.length === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.compute_dynamics</code> after{" "}
          <code className="text-white">ingest_yahoo</code>, then refresh.
        </p>
      ) : null}

      <section className="overflow-hidden rounded border border-line bg-panel">
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <h2 className="text-[11px] uppercase tracking-wide text-mute">RRG</h2>
          <p className="text-[11px] text-mute">
            <span className="text-up">Leading</span>
            <span className="mx-1.5 text-line">·</span>
            <span className="text-[#d4a017]">Weakening</span>
            <span className="mx-1.5 text-line">·</span>
            <span className="text-down">Lagging</span>
            <span className="mx-1.5 text-line">·</span>
            <span className="text-[#6cb6ff]">Improving</span>
          </p>
        </div>
        <RrgScatter members={tape.members} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {QUADRANTS.map((quadrant) => (
          <QuadrantList
            key={quadrant.id}
            title={quadrant.label}
            accent={QUADRANT_DOT[quadrant.id]}
            items={grouped[quadrant.id]}
          />
        ))}
      </section>

      <section className="overflow-hidden rounded border border-line bg-panel">
        <div className="border-b border-line px-3 py-2">
          <h2 className="text-[11px] uppercase tracking-wide text-mute">
            Relative vs {tape.benchmark} (63 sessions, 100 at start)
          </h2>
        </div>
        <RelativeOverlay series={tape.overlay ?? []} benchmark={tape.benchmark} />
      </section>

      <SectorTable rows={sectors} />
      <CorrHeatmap corr={tape.corr} />
      <LeadLagPanel
        pair={tape.lead_lag}
        tickers={pairTickers}
        asOf={asOf ?? tape.as_of}
      />
    </div>
  );
}

function QuadrantList({
  title,
  accent,
  items,
}: {
  title: string;
  accent: string;
  items: DynamicsMember[];
}) {
  return (
    <div className="overflow-hidden rounded border border-line">
      <h2 className="flex items-center gap-2 border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        <span className={cn("h-1.5 w-1.5 rounded-full", accent)} />
        {title}
        <span className="ml-auto tabular-nums">{items.length}</span>
      </h2>
      {items.length === 0 ? (
        <p className="px-3 py-3 text-[13px] text-mute">None</p>
      ) : (
        items.map((item, index) => (
          <div
            key={item.ticker}
            className={cn(
              "flex items-center gap-3 px-3 py-2",
              index < items.length - 1 ? "border-b border-line" : "",
            )}
          >
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium">{item.ticker}</p>
              <p className="truncate text-[11px] text-mute">{item.sector ?? item.name}</p>
            </div>
            <Spark points={item.indexed} />
            <span className={cn("w-14 text-right text-[13px] tabular-nums", changeClass(item.ret_1m))}>
              {formatPct(item.ret_1m)}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

function Spark({ points }: { points: { date: string; value: number }[] }) {
  if (points.length < 2) {
    return <span className="w-[72px] shrink-0" />;
  }
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 72;
  const height = 24;
  const d = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * (height - 2) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <polyline fill="none" stroke={up ? "#3dd68c" : "#ef5b5b"} strokeWidth="1.25" points={d} />
    </svg>
  );
}

function SectorTable({ rows }: { rows: DynamicsMember[] }) {
  return (
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        US sectors
      </h2>
      {rows.length === 0 ? (
        <p className="px-3 py-3 text-sm text-mute">
          No sector rows. Run <code className="text-white">python -m jobs.compute_dynamics</code>.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wide text-mute">
              <tr className="border-b border-line">
                <th className="px-3 py-2 font-normal">Ticker</th>
                <th className="px-3 py-2 font-normal">Sector</th>
                <th className="px-3 py-2 font-normal">Quad</th>
                <th className="px-3 py-2 text-right font-normal">RS</th>
                <th className="px-3 py-2 text-right font-normal">1W</th>
                <th className="px-3 py-2 text-right font-normal">1M</th>
                <th className="px-3 py-2 text-right font-normal">3M</th>
                <th className="px-3 py-2 text-right font-normal">1Y</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.ticker} className="border-b border-line last:border-0">
                  <td className="px-3 py-2 font-medium">{item.ticker}</td>
                  <td className="px-3 py-2 text-mute">{item.sector ?? item.name}</td>
                  <td className="px-3 py-2 capitalize text-mute">{item.quadrant}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{item.rs_ratio.toFixed(1)}</td>
                  <td className={cn("px-3 py-2 text-right tabular-nums", changeClass(item.ret_1w))}>
                    {formatPct(item.ret_1w)}
                  </td>
                  <td className={cn("px-3 py-2 text-right tabular-nums", changeClass(item.ret_1m))}>
                    {formatPct(item.ret_1m)}
                  </td>
                  <td className={cn("px-3 py-2 text-right tabular-nums", changeClass(item.ret_3m))}>
                    {formatPct(item.ret_3m)}
                  </td>
                  <td className={cn("px-3 py-2 text-right tabular-nums", changeClass(item.ret_1y))}>
                    {formatPct(item.ret_1y)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CorrHeatmap({ corr }: { corr: DynamicsCorr | null }) {
  if (corr == null || corr.tickers.length === 0) {
    return (
      <section className="overflow-hidden rounded border border-line">
        <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
          63-session correlation
        </h2>
        <p className="px-3 py-3 text-sm text-mute">Not enough overlapping sector bars for a matrix.</p>
      </section>
    );
  }
  return (
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        {corr.window}-session correlation
      </h2>
      <div className="overflow-x-auto p-3">
        <table className="border-collapse text-[11px] tabular-nums">
          <thead>
            <tr>
              <th className="p-1" />
              {corr.tickers.map((ticker) => (
                <th key={ticker} className="p-1 text-center font-normal text-mute">
                  {ticker}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {corr.tickers.map((rowTicker, i) => (
              <tr key={rowTicker}>
                <th className="pr-2 text-left font-normal text-mute">{rowTicker}</th>
                {corr.matrix[i]?.map((value, j) => (
                  <td
                    key={`${rowTicker}-${corr.tickers[j]}`}
                    className="h-8 min-w-8 p-0 text-center"
                    style={corrCell(value)}
                    title={`${rowTicker} / ${corr.tickers[j]}: ${value == null ? "n/a" : value.toFixed(2)}`}
                  >
                    {value == null ? "—" : value.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function LeadLagPanel({
  pair,
  tickers,
  asOf,
}: {
  pair: DynamicsLeadLag | null;
  tickers: string[];
  asOf: string | null | undefined;
}) {
  const left = pair?.left ?? "XLK";
  const right = pair?.right ?? "XLF";
  return (
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        Lead-lag (−5…+5 sessions)
      </h2>
      <div className="space-y-3 px-3 py-3">
        <p className="text-[13px] text-mute">{pair?.note ?? "Pick two sector ETFs."}</p>
        {tickers.length > 0 ? (
          <>
            <ChipRow
              label="Lead"
              selected={left}
              tickers={tickers}
              hrefFor={(ticker) => dynamicsHref({ asOf, lead: ticker, lag: right })}
            />
            <ChipRow
              label="Lag"
              selected={right}
              tickers={tickers}
              hrefFor={(ticker) => dynamicsHref({ asOf, lead: left, lag: ticker })}
            />
          </>
        ) : null}
        {pair ? <LagBars bars={pair.bars} peak={pair.peak_lag} /> : null}
      </div>
    </section>
  );
}

function ChipRow({
  label,
  selected,
  tickers,
  hrefFor,
}: {
  label: string;
  selected: string;
  tickers: string[];
  hrefFor: (ticker: string) => string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-10 text-[11px] uppercase tracking-wide text-mute">{label}</span>
      {tickers.map((ticker) => (
        <Link
          key={`${label}-${ticker}`}
          href={hrefFor(ticker)}
          className={cn(
            "rounded border px-2 py-0.5 text-[12px]",
            ticker === selected ? "border-white/40 text-white" : "border-line text-mute hover:text-white",
          )}
        >
          {ticker}
        </Link>
      ))}
    </div>
  );
}

function LagBars({
  bars,
  peak,
}: {
  bars: { lag: number; corr: number | null }[];
  peak: number | null;
}) {
  return (
    <div className="grid grid-cols-11 gap-1 pt-1">
      {bars.map((bar) => {
        const height = bar.corr == null ? 0 : Math.abs(bar.corr) * 64;
        const up = (bar.corr ?? 0) >= 0;
        return (
          <div key={bar.lag} className="flex flex-col items-center gap-1">
            <div className="flex h-16 w-full items-end justify-center rounded bg-ink">
              <div
                className={cn("w-3 rounded-sm", up ? "bg-up/80" : "bg-down/80", bar.lag === peak ? "ring-1 ring-white/50" : "")}
                style={{ height }}
              />
            </div>
            <span className="text-[10px] text-mute">{bar.lag > 0 ? `+${bar.lag}` : bar.lag}</span>
          </div>
        );
      })}
    </div>
  );
}

function dynamicsHref({
  asOf,
  lead,
  lag,
}: {
  asOf?: string | null;
  lead: string;
  lag: string;
}): string {
  const query = new URLSearchParams({ lead, lag });
  if (asOf) {
    query.set("as_of", asOf);
  }
  return `/dynamics?${query.toString()}`;
}

function corrCell(value: number | null): { background: string; color: string } {
  if (value == null) {
    return { background: "#101010", color: "#8a8a8a" };
  }
  const alpha = Math.min(1, Math.abs(value)) * 0.55;
  const rgb = value >= 0 ? "61, 214, 140" : "239, 91, 91";
  return { background: `rgba(${rgb}, ${alpha})`, color: "#ececec" };
}

function formatPct(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  const abs = Math.abs(value).toFixed(1);
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
