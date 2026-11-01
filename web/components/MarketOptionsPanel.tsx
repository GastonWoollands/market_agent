"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MarketOptions } from "@/lib/api";
import { DASH, fmtNumber, fmtPct } from "@/lib/format";

// Validated against the #0a0e14 surface (same pair as the credit curve: today vs context).
const MAIN = "#3b82f6";
const CONTEXT = "#64748b";
const AXIS = { fill: "#94a3b8", fontSize: 11 };
const GRID = "#1f2633";

export function MarketOptionsPanel({ market }: { market: MarketOptions | null }) {
  if (market == null) {
    return <p className="text-[13px] text-mute">Options API unreachable.</p>;
  }
  const front = market.vix_curve.find((point) => point.ticker === "^VIX")?.value ?? null;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="VIX ÷ VIX3M"
          value={fmtNumber(market.vix_ratio)}
          note={
            market.vix_ratio == null
              ? undefined
              : market.vix_ratio >= 1
                ? "backwardation: near-term fear above 3m"
                : "contango: calm, near-term below 3m"
          }
        />
        {market.indices.map((row) => (
          <Tile
            key={row.ticker}
            label={row.label}
            value={fmtNumber(row.value)}
            note={[
              row.change_1d == null ? null : `${row.change_1d >= 0 ? "+" : "−"}${Math.abs(row.change_1d).toFixed(2)} 1d`,
              row.pct_1y == null ? null : `${fmtPct(row.pct_1y, 0)} 1y percentile`,
            ]
              .filter(Boolean)
              .join(" · ")}
          />
        ))}
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-wide text-mute">VIX ÷ VIX3M, 1y</h3>
          <p className="mb-2 text-[11px] text-mute">
            Curve today: 9d {fmtNumber(market.vix_curve[0]?.value)} · 30d {fmtNumber(front)} · 3m{" "}
            {fmtNumber(market.vix_curve[2]?.value)}. Above 1 is inverted.
          </p>
          <div className="h-[220px] w-full" aria-label="VIX to VIX3M ratio over the last year">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={market.vix_ratio_history} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="date" tick={AXIS} axisLine={false} tickLine={false} minTickGap={48} tickFormatter={month} />
                <YAxis domain={["auto", "auto"]} tick={AXIS} axisLine={false} tickLine={false} width={40} />
                <ReferenceLine y={1} stroke="#94a3b8" strokeDasharray="3 3" />
                <Tooltip
                  cursor={{ stroke: "#384152" }}
                  content={({ active, payload }) => {
                    const row = active ? payload?.[0]?.payload : undefined;
                    return row ? <Tip head={row.date} lines={[`ratio ${fmtNumber(row.ratio)}`]} /> : null;
                  }}
                />
                <Line dataKey="ratio" stroke={MAIN} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <h3 className="text-[11px] uppercase tracking-wide text-mute">Equity put/call, Cboe, 1y</h3>
          <p className="mb-2 text-[11px] text-mute">
            {market.put_call
              .map((row) => `${row.label} ${fmtNumber(row.ratio)}${row.pct_1y == null ? "" : ` (${fmtPct(row.pct_1y, 0)})`}`)
              .join(" · ")}
            {market.put_call_as_of ? ` · ${market.put_call_as_of}` : ""}
          </p>
          <div className="h-[220px] w-full" aria-label="Cboe equity put/call ratio, daily and 10-day mean">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={market.put_call_history} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="date" tick={AXIS} axisLine={false} tickLine={false} minTickGap={48} tickFormatter={month} />
                <YAxis domain={["auto", "auto"]} tick={AXIS} axisLine={false} tickLine={false} width={40} />
                <Tooltip
                  cursor={{ stroke: "#384152" }}
                  content={({ active, payload }) => {
                    const row = active ? payload?.[0]?.payload : undefined;
                    return row ? (
                      <Tip
                        head={row.date}
                        lines={[`daily ${fmtNumber(row.equity)}`, `10d mean ${fmtNumber(row.equity_10d)}`]}
                      />
                    ) : null;
                  }}
                />
                <Line dataKey="equity" stroke={CONTEXT} strokeWidth={1} dot={false} isAnimationActive={false} />
                <Line dataKey="equity_10d" stroke={MAIN} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex gap-4 text-[11px] text-mute">
            <Key color={CONTEXT} label="Daily" />
            <Key color={MAIN} label="10-day mean" />
          </div>
        </div>
      </div>
      <p className="text-[11px] leading-5 text-mute">
        Percentiles are against the last year of stored sessions. Cboe ratios count Cboe-listed
        volume only, not every US venue. A high equity put/call reads as hedging demand; it is
        context, not a timing signal.
      </p>
    </div>
  );
}

function month(value: string): string {
  return value ? value.slice(0, 7) : DASH;
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded border border-line p-3">
      <div className="text-[11px] text-mute">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      {note ? <div className="text-[11px] text-mute">{note}</div> : null}
    </div>
  );
}

function Tip({ head, lines }: { head: string; lines: string[] }) {
  return (
    <div className="rounded border border-line bg-panel px-2 py-1 text-[12px]">
      <div className="text-text-secondary">{head}</div>
      {lines.map((line) => (
        <div key={line} className="tabular-nums text-text-primary">
          {line}
        </div>
      ))}
    </div>
  );
}

function Key({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-0.5 w-3" style={{ background: color }} />
      {label}
    </span>
  );
}
