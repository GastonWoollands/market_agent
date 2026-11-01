"use client";

import type { ReactElement } from "react";
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

import { Panel } from "@/components/Panel";
import type { TickerOptions } from "@/lib/api";
import { DASH, fmtNumber, fmtPct } from "@/lib/format";

const LINE = "#3b82f6";
const AXIS = { fill: "#94a3b8", fontSize: 11 };
const GRID = "#1f2633";

export function OptionsPanel({ options }: { options: TickerOptions | null }) {
  if (!options) {
    return null;
  }
  if (options.as_of == null) {
    return (
      <Panel title="Options read">
        <p className="text-[13px] text-mute">{options.unavailable ?? "No stored chain."}</p>
      </Panel>
    );
  }
  const note = `Yahoo chains, monthly expiries · close ${options.as_of}`;
  return (
    <Panel title="Options read" note={note}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Item label="ATM IV 30d" value={fmtPct(options.atm_iv_30d, 1)} />
        <Item
          label="IV ÷ 1y realized"
          value={options.iv_rv == null ? DASH : `${fmtNumber(options.iv_rv)}×`}
          note={options.rv_1y == null ? undefined : `realized ${fmtPct(options.rv_1y, 0)}`}
        />
        <Item
          label="IV rank 1y"
          value={options.iv_rank == null ? DASH : fmtPct(options.iv_rank, 0)}
          note={options.iv_rank == null ? `after 252 sessions (${options.iv_sessions} stored)` : undefined}
        />
        <Item
          label="Term 90d − 30d"
          value={fmtVolPoints(options.term_slope)}
          note={slopeNote(options.term_slope)}
        />
        <Item
          label="Skew 30d"
          value={fmtVolPoints(options.skew_30d)}
          note="90% put IV − 110% call IV"
        />
        <Item label="Put/call volume" value={fmtNumber(options.pc_volume)} />
        <Item label="Put/call open interest" value={fmtNumber(options.pc_oi)} />
        <Item
          label="Expected move"
          value={options.expected_move == null ? DASH : `±${fmtPct(options.expected_move, 1)}`}
          note={moveNote(options)}
        />
      </dl>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Chart title="ATM IV by expiry" empty={options.term.length < 2}>
          <LineChart data={options.term} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="dte"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(value: number) => `${value}d`}
              tick={AXIS}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(value: number) => `${(value * 100).toFixed(1)}%`}
              domain={["auto", "auto"]}
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip
              cursor={{ stroke: "#384152" }}
              content={({ active, payload }) => {
                const row = active ? payload?.[0]?.payload : undefined;
                return row ? (
                  <Tip head={`${row.expiry} · ${row.dte}d`} body={`ATM IV ${fmtPct(row.atm_iv, 1)}`} />
                ) : null;
              }}
            />
            <Line
              dataKey="atm_iv"
              stroke={LINE}
              strokeWidth={2}
              dot={{ r: 4, fill: LINE, stroke: "#0a0e14", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </Chart>
        <Chart
          title={`Smile, ${options.smile_expiry ?? DASH} (OTM puts left, calls right)`}
          empty={options.smile.length < 3}
        >
          <LineChart data={options.smile} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="moneyness"
              type="number"
              domain={[0.7, 1.3]}
              ticks={[0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.3]}
              tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              tick={AXIS}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              domain={["auto", "auto"]}
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <ReferenceLine x={1} stroke="#384152" strokeDasharray="3 3" />
            <Tooltip
              cursor={{ stroke: "#384152" }}
              content={({ active, payload }) => {
                const row = active ? payload?.[0]?.payload : undefined;
                return row ? (
                  <Tip
                    head={`Strike ${Math.round(row.moneyness * 100)}% of spot · ${row.kind === "P" ? "put" : "call"}`}
                    body={`IV ${fmtPct(row.iv, 1)}`}
                  />
                ) : null;
              }}
            />
            <Line
              dataKey="iv"
              stroke={LINE}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: LINE, stroke: "#0a0e14", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </Chart>
      </div>
      <p className="mt-4 text-[11px] leading-5 text-mute">
        IV is Black-Scholes on the bid/ask mid (or a same-session trade when the quote is wide),
        out-of-the-money side only; 30d and 90d interpolate in total variance. Put/call counts the
        stored monthly expiries within ±30% of spot, not the whole chain. Not a rank input.
      </p>
    </Panel>
  );
}

function fmtVolPoints(value: number | null): string {
  if (value == null) {
    return DASH;
  }
  const points = value * 100;
  return `${points >= 0 ? "+" : "−"}${Math.abs(points).toFixed(1)} pts`;
}

function slopeNote(value: number | null): string | undefined {
  if (value == null) {
    return undefined;
  }
  return value < 0 ? "inverted: near-term stress priced" : "upward: normal";
}

function moveNote(options: TickerOptions): string | undefined {
  if (options.earnings_date == null) {
    return "no earnings date";
  }
  const date = `${options.earnings_estimate ? "est. " : ""}${options.earnings_date}`;
  if (options.expected_move == null) {
    return `earnings ${date}; read within 45 days`;
  }
  return `earnings ${date}, straddle to ${options.move_expiry}`;
}

function Chart({
  title,
  empty,
  children,
}: {
  title: string;
  empty: boolean;
  children: ReactElement;
}) {
  return (
    <div>
      <div className="mb-1 text-[11px] text-mute">{title}</div>
      {empty ? (
        <p className="text-[12px] text-mute">Too few quoted strikes to draw.</p>
      ) : (
        <div className="h-[200px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function Tip({ head, body }: { head: string; body: string }) {
  return (
    <div className="rounded border border-line bg-panel px-2 py-1 text-[12px]">
      <div className="text-text-secondary">{head}</div>
      <div className="tabular-nums text-text-primary">{body}</div>
    </div>
  );
}

function Item({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-[11px] text-mute">{label}</dt>
      <dd className="text-[14px] tabular-nums">{value}</dd>
      {note ? <dd className="text-[10px] text-mute">{note}</dd> : null}
    </div>
  );
}
