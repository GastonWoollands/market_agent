"use client";

import {
  CartesianGrid,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DynamicsMember } from "@/lib/api";

const QUADRANT_COLOR: Record<string, string> = {
  leading: "#3dd68c",
  weakening: "#d4a017",
  lagging: "#ef5b5b",
  improving: "#6cb6ff",
};

export function RrgScatter({ members }: { members: DynamicsMember[] }) {
  if (members.length === 0) {
    return (
      <p className="px-3 py-8 text-sm text-mute">
        No RRG points yet. Run <code className="text-white">python -m jobs.compute_dynamics</code> after
        Yahoo bars are in Postgres.
      </p>
    );
  }

  const values = members.flatMap((item) => [
    item.rs_ratio,
    item.rs_momentum,
    ...item.trail.flatMap((point) => [point.rs_ratio, point.rs_momentum]),
  ]);
  const lo = Math.min(100, ...values);
  const hi = Math.max(100, ...values);
  const pad = Math.max(1.5, (hi - lo) * 0.12);
  const domain: [number, number] = [Math.floor(lo - pad), Math.ceil(hi + pad)];

  return (
    <div className="h-[28rem] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 28, right: 28, left: 8, bottom: 12 }}>
          <CartesianGrid stroke="#222222" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="rs_ratio"
            name="RS-Ratio"
            domain={domain}
            tick={{ fill: "#8a8a8a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="number"
            dataKey="rs_momentum"
            name="RS-Momentum"
            domain={domain}
            tick={{ fill: "#8a8a8a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={48}
          />
          <ReferenceLine x={100} stroke="#444444" />
          <ReferenceLine y={100} stroke="#444444" />
          <Tooltip
            cursor={{ stroke: "#333333" }}
            contentStyle={{
              background: "#101010",
              border: "1px solid #222222",
              fontSize: 12,
            }}
            formatter={(value: number, name: string) => [value.toFixed(2), name]}
          />
          {members.map((item) =>
            item.trail.length > 1 ? (
              <Scatter
                key={`${item.ticker}-trail`}
                data={item.trail.map((point) => ({
                  rs_ratio: point.rs_ratio,
                  rs_momentum: point.rs_momentum,
                }))}
                line
                lineType="joint"
                shape={() => <g />}
                legendType="none"
                fill="none"
                stroke="#3a3a3a"
                strokeWidth={1}
                isAnimationActive={false}
              />
            ) : null,
          )}
          {members.map((item) => (
            <Scatter
              key={item.ticker}
              name={item.ticker}
              data={[
                {
                  ticker: item.ticker,
                  rs_ratio: item.rs_ratio,
                  rs_momentum: item.rs_momentum,
                },
              ]}
              fill={QUADRANT_COLOR[item.quadrant] ?? "#ececec"}
              isAnimationActive={false}
            >
              <LabelList dataKey="ticker" position="top" fill="#8a8a8a" fontSize={10} />
            </Scatter>
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
