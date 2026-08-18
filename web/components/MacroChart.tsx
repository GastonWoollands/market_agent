"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { LivePoint } from "@/lib/api";

export function MacroChart({
  points,
  unit,
  positive,
}: {
  points: LivePoint[];
  unit: string;
  positive: boolean;
}) {
  if (points.length < 2) {
    return <p className="px-3 py-8 text-sm text-mute">Not enough stored history for a chart.</p>;
  }

  const stroke = positive ? "#3dd68c" : "#ef5b5b";
  const data = points.map((point) => ({ date: point.date, value: point.value }));

  return (
    <div className="h-56 w-full">
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
            width={56}
            tickFormatter={(value: number) => formatAxis(unit, value)}
            tick={{ fill: "#8a8a8a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#101010",
              border: "1px solid #222222",
              fontSize: 12,
            }}
            labelFormatter={(label) => String(label)}
            formatter={(value) => [formatAxis(unit, Number(value)), ""]}
          />
          <Line type="monotone" dataKey="value" dot={false} stroke={stroke} strokeWidth={1.5} />
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

function formatAxis(unit: string, value: number): string {
  if (unit === "percent") {
    return `${value.toFixed(2)}%`;
  }
  return value.toFixed(2);
}
