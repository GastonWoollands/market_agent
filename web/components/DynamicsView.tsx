import { Fragment } from "react";

import { StaleBadge } from "@/components/StaleBadge";
import { CorrHeatmap } from "@/components/CorrHeatmap";
import { LeadLagPanel } from "@/components/LeadLagPanel";
import { RelativeOverlay } from "@/components/RelativeOverlay";
import { RotationPanel } from "@/components/RotationPanel";
import { cn } from "@/lib/cn";
import type { DynamicsMember, DynamicsTape } from "@/lib/api";
import {
  QUADRANT_COLOR,
  QUADRANT_TEXT,
  QUADRANTS,
  displayName,
  nameByTicker,
} from "@/lib/dynamics";

export function DynamicsView({ tape, asOf }: { tape: DynamicsTape | null; asOf?: string }) {
  if (tape == null) {
    return <p className="text-sm text-mute">Dynamics API unreachable. Start uvicorn, then refresh.</p>;
  }

  const names = nameByTicker(tape.members);
  const pairOptions = Array.from(
    new Set([...tape.members.map((item) => item.ticker), ...(tape.corr?.tickers ?? [])]),
  )
    .map((ticker) => ({ ticker, name: names[ticker] ?? ticker }))
    .sort((a, b) => a.name.localeCompare(b.name) || a.ticker.localeCompare(b.ticker));
  const overlayColors = Object.fromEntries(
    tape.members.map((item) => [item.ticker, QUADRANT_COLOR[item.quadrant] ?? "#8a8a8a"]),
  );
  const sectors = tape.members
    .slice()
    .sort((a, b) => (b.ret_3m ?? -Infinity) - (a.ret_3m ?? -Infinity));

  return (
    <div className="space-y-12">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-semibold tracking-tight">Dynamics</h1>
          <p className="mt-2 text-sm leading-6 text-mute">
            How the sector groups move relative to each other — who is leading, who is fading, and
            whether any of it is predictable.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.as_of ? <>as of {tape.as_of}</> : "no rows"}
          {tape.stale ? (
            <>
              <span className="mx-2 text-line">·</span>
              <StaleBadge stale />
            </>
          ) : null}
        </p>
      </div>

      {tape.members.length === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.compute_dynamics</code> after{" "}
          <code className="text-white">ingest_yahoo</code>, then refresh.
        </p>
      ) : (
        <section className="space-y-4">
          <h2 className="text-sm font-medium">Sector rotation vs the S&P 500 ({tape.benchmark})</h2>
          <RotationSummary members={tape.members} benchmark={tape.benchmark} />
          <RotationPanel members={tape.members} benchmark={tape.benchmark} />
        </section>
      )}

      {tape.members.length > 0 ? (
        <div className="grid gap-12 lg:grid-cols-2 lg:items-start">
          <section className="space-y-3">
            <h2 className="text-sm font-medium">Do sectors move together?</h2>
            <p className="max-w-xl text-[13px] leading-6 text-mute">
              Pairwise correlation of daily returns over the same stored window. Low readings mean
              sectors are moving independently — useful context for concentration, not a forecast.
            </p>
            <CorrHeatmap corr={tape.corr} names={names} />
          </section>
          <section className="space-y-3">
            <h2 className="text-sm font-medium">Does any sector move first?</h2>
            <p className="max-w-xl text-[13px] leading-6 text-mute">
              Cross-correlation at lags −5 to +5 sessions for one pair. Same-day peaks are the usual
              finding — not identified leadership.
            </p>
            <LeadLagPanel pair={tape.lead_lag} options={pairOptions} asOf={asOf} />
          </section>
        </div>
      ) : null}

      {tape.members.length > 0 ? (
        <div className="space-y-3">
          <details>
            <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-mute hover:text-white">
              Relative vs {tape.benchmark} (63 sessions, 100 at start)
            </summary>
            <div className="mt-3 overflow-hidden rounded border border-line bg-panel">
              <RelativeOverlay series={tape.overlay ?? []} benchmark={tape.benchmark} colors={overlayColors} />
            </div>
          </details>
          <details>
            <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-mute hover:text-white">
              Absolute returns
            </summary>
            <div className="mt-3">
              <SectorTable rows={sectors} />
            </div>
          </details>
        </div>
      ) : null}
    </div>
  );
}

function RotationSummary({
  members,
  benchmark,
}: {
  members: DynamicsMember[];
  benchmark: string;
}) {
  const groups = QUADRANTS.map((quadrant) => ({
    ...quadrant,
    items: members.filter((item) => item.quadrant === quadrant.id),
  })).filter((group) => group.items.length > 0);
  if (groups.length === 0) {
    return null;
  }
  return (
    <p className="max-w-3xl text-[13px] leading-6 text-mute">
      {groups.map((group, index) => (
        <Fragment key={group.id}>
          {index > 0 ? " " : null}
          <NameList items={group.items} />
          {group.id === "leading"
            ? ` ${group.items.length === 1 ? "is" : "are"} Leading versus ${benchmark}.`
            : group.id === "weakening"
              ? ` ${group.items.length === 1 ? "is" : "are"} still strong but fading.`
              : group.id === "improving"
                ? ` ${group.items.length === 1 ? "is" : "are"} Improving.`
                : ` ${group.items.length === 1 ? "remains" : "remain"} Lagging.`}
        </Fragment>
      ))}
    </p>
  );
}

function NameList({ items }: { items: DynamicsMember[] }) {
  const shown = items.slice(0, 4);
  const rest = items.length - shown.length;
  return (
    <>
      {shown.map((item, index) => (
        <Fragment key={item.ticker}>
          {index > 0 && index === shown.length - 1 && rest === 0 ? " and " : index > 0 ? ", " : null}
          <span className={cn("font-medium", QUADRANT_TEXT[item.quadrant])}>{displayName(item)}</span>
        </Fragment>
      ))}
      {rest > 0 ? ` and ${rest} more` : null}
    </>
  );
}

function SectorTable({ rows }: { rows: DynamicsMember[] }) {
  return (
    <div className="overflow-hidden rounded border border-line">
      {rows.length === 0 ? (
        <p className="px-3 py-3 text-sm text-mute">No sector rows.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wide text-mute">
              <tr className="border-b border-line">
                <th className="px-3 py-2 font-normal">Name</th>
                <th className="px-3 py-2 font-normal">Ticker</th>
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
                  <td className="px-3 py-2">{displayName(item)}</td>
                  <td className="px-3 py-2 font-medium">{item.ticker}</td>
                  <td className={cn("px-3 py-2 capitalize", QUADRANT_TEXT[item.quadrant])}>
                    {item.quadrant}
                  </td>
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
    </div>
  );
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
