"use client";

import {
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { StaleBadge } from "@/components/StaleBadge";
import { cn } from "@/lib/cn";
import type { CreditCurve } from "@/lib/api";
import { DASH, fmtNumber } from "@/lib/format";

const TODAY_COLOR = "#3b82f6";
const YEAR_AGO_COLOR = "#64748b";
const AXIS = { fill: "#94a3b8", fontSize: 11 };

export function CreditCurvePanel({ curve }: { curve: CreditCurve | null }) {
  return (
    <section className="rounded border border-line p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-[11px] uppercase tracking-wide text-mute">Credit curve by rating</h2>
        <span className="text-[11px] text-mute">
          ICE BofA OAS, FRED{curve?.as_of ? ` · ${curve.as_of}` : ""}
          {curve?.stale ? (
            <>
              {" "}
              <StaleBadge stale />
            </>
          ) : null}
        </span>
      </div>
      {curve == null || curve.buckets.every((item) => item.oas_bp == null) ? (
        <p className="text-[13px] text-mute">
          No stored rating curve. Run <code className="text-white">python -m jobs.ingest_fred</code>.
        </p>
      ) : (
        <CurveBody curve={curve} />
      )}
    </section>
  );
}

function CurveBody({ curve }: { curve: CreditCurve }) {
  const data = curve.buckets.map((item) => ({
    rating: item.rating,
    today: item.oas_bp,
    yearAgo: item.oas_1y_bp,
  }));
  return (
    <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
      <div>
        <div className="h-[240px] w-full" aria-label="Option-adjusted spread by rating, today and one year ago">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 18, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1a1f26" vertical={false} />
              <XAxis dataKey="rating" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis
                scale="log"
                domain={[20, 2000]}
                ticks={[25, 50, 100, 200, 500, 1000, 2000]}
                tick={AXIS}
                axisLine={false}
                tickLine={false}
                width={44}
                tickFormatter={(value: number) => `${value}`}
              />
              <Tooltip
                contentStyle={{ background: "#0f1419", border: "1px solid #262d38", fontSize: 12 }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(value: number, name: string) => [`${Math.round(value)} bp`, name]}
              />
              <Line
                dataKey="yearAgo"
                name="1y ago"
                stroke={YEAR_AGO_COLOR}
                strokeWidth={2}
                strokeDasharray="4 3"
                dot={{ r: 4, fill: YEAR_AGO_COLOR, stroke: "#0a0e14", strokeWidth: 2 }}
                isAnimationActive={false}
              />
              <Line
                dataKey="today"
                name="Today"
                stroke={TODAY_COLOR}
                strokeWidth={2}
                dot={{ r: 4, fill: TODAY_COLOR, stroke: "#0a0e14", strokeWidth: 2 }}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey="today"
                  position="top"
                  offset={8}
                  style={{ fill: "#e2e8f0", fontSize: 11 }}
                  formatter={(value: number) => Math.round(value)}
                />
              </Line>
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 text-[11px] text-mute">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4" style={{ background: TODAY_COLOR }} /> Today (bp)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: YEAR_AGO_COLOR }} />{" "}
            1y ago
          </span>
          <span>log scale</span>
        </div>
      </div>
      <div>
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr className="border-b border-line text-[11px] uppercase tracking-wide text-mute">
              <th className="px-2 py-1.5 font-normal">Rating</th>
              <th className="px-2 py-1.5 text-right font-normal">OAS</th>
              <th className="px-2 py-1.5 text-right font-normal">Δ 1m</th>
              <th className="px-2 py-1.5 text-right font-normal">Δ 1y</th>
              <th className="px-2 py-1.5 text-right font-normal">Yield</th>
            </tr>
          </thead>
          <tbody>
            {curve.buckets.map((item) => (
              <tr key={item.rating} className="border-b border-line last:border-0">
                <td className="px-2 py-1.5">
                  {item.rating} <span className="text-[11px] text-mute">{item.grade}</span>
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">{bp(item.oas_bp)}</td>
                <Delta now={item.oas_bp} before={item.oas_1m_bp} />
                <Delta now={item.oas_bp} before={item.oas_1y_bp} />
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {item.yield_pct == null ? DASH : `${item.yield_pct.toFixed(2)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
          <Gauge label="Baa − 10Y" value={bp(curve.baa_10y_bp)} />
          <Gauge label="NFCI" value={fmtNumber(curve.nfci)} note={curve.nfci_as_of ?? undefined} />
          <Gauge label="STL stress" value={fmtNumber(curve.stlfsi)} note={curve.stlfsi_as_of ?? undefined} />
        </dl>
        <p className="mt-2 text-[11px] text-mute">NFCI / stress: 0 = average conditions, above 0 = tighter.</p>
      </div>
    </div>
  );
}

// Wider spreads are worse for credit: widening reads red, tightening green.
function Delta({ now, before }: { now: number | null; before: number | null }) {
  if (now == null || before == null) {
    return <td className="px-2 py-1.5 text-right tabular-nums text-mute">{DASH}</td>;
  }
  const change = Math.round(now - before);
  return (
    <td
      className={cn(
        "px-2 py-1.5 text-right tabular-nums",
        change > 0 ? "text-down" : change < 0 ? "text-up" : "text-mute",
      )}
    >
      {change > 0 ? "+" : ""}
      {change}
    </td>
  );
}

function Gauge({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-[11px] text-mute">{label}</dt>
      <dd className="tabular-nums">{value}</dd>
      {note ? <dd className="text-[10px] text-mute">{note}</dd> : null}
    </div>
  );
}

function bp(value: number | null): string {
  return value == null ? DASH : `${Math.round(value)}`;
}
