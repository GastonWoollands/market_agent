"use client";

import {
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DynamicsOverlay } from "@/lib/api";

const PALETTE = [
  "#6cb6ff",
  "#c678dd",
  "#56b6c2",
  "#d19a66",
  "#e6c07b",
  "#98c379",
  "#e06c75",
  "#61afef",
  "#abb2bf",
  "#be5046",
  "#d4a017",
];

export function RelativeOverlay({
  series,
  benchmark,
}: {
  series: DynamicsOverlay[];
  benchmark: string;
}) {
  if (series.length === 0) {
    return (
      <p className="px-3 py-8 text-sm text-mute">
        Not enough stored bars for a relative overlay. Run{" "}
        <code className="text-white">python -m jobs.ingest_yahoo</code>.
      </p>
    );
  }

  const dates = [...new Set(series.flatMap((item) => item.points.map((point) => point.date)))].sort();
  const lookup = new Map(
    series.map((item) => [item.ticker, new Map(item.points.map((point) => [point.date, point.value]))]),
  );
  const data = dates.map((day) => {
    const row: Record<string, string | number | null> = { date: day };
    for (const item of series) {
      row[item.ticker] = lookup.get(item.ticker)?.get(day) ?? null;
    }
    return row;
  });

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tickFormatter={formatTickDate}
            minTickGap={40}
            tick={{ fill: "#8a8a8a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            orientation="right"
            domain={["auto", "auto"]}
            width={48}
            tick={{ fill: "#8a8a8a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value: number) => value.toFixed(0)}
          />
          <ReferenceLine y={100} stroke="#444444" />
          <Tooltip
            contentStyle={{
              background: "#101010",
              border: "1px solid #222222",
              fontSize: 12,
            }}
            formatter={(value: number, name: string) => [Number(value).toFixed(2), name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#8a8a8a" }} />
          {series.map((item, index) => (
            <Line
              key={item.ticker}
              type="monotone"
              dataKey={item.ticker}
              name={item.ticker}
              dot={false}
              stroke={PALETTE[index % PALETTE.length]}
              strokeWidth={item.ticker === benchmark ? 1.8 : 1.25}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatTickDate(value: string): string {
  const parts = value.split("-");
  if (parts.length < 3) {
    return value;
  }
  return `${parts[1]}/${parts[2]}`;
}
