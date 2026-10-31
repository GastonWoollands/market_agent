"use client";

import {
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import type { PeerPoint } from "@/lib/api";
import { fmtMultiple, fmtSignedPct } from "@/lib/format";

// Validated against the #0a0e14 surface (dataviz validator, dark mode).
export const SELF_COLOR = "#3b82f6";
export const PEER_COLOR = "#c4800f";
const SECTOR_COLOR = "#475569";
const AXIS = { fill: "#94a3b8", fontSize: 11 };

// Outliers would flatten the cloud; they are pinned to the edge and counted.
const GROWTH_RANGE: [number, number] = [-0.5, 1.5];
const MULTIPLE_RANGE: [number, number] = [2, 100];

type Dot = PeerPoint & { x: number; y: number; clipped: boolean };

export function PeerScatter({
  points,
  peers,
  medianMultiple,
  medianGrowth,
}: {
  points: PeerPoint[];
  peers: string[];
  medianMultiple: number | null;
  medianGrowth: number | null;
}) {
  const peerSet = new Set(peers);
  const dots: Dot[] = points.map((point) => {
    const x = clamp(point.ebitda_growth_1y, GROWTH_RANGE);
    const y = clamp(point.ev_ebitda, MULTIPLE_RANGE);
    return { ...point, x, y, clipped: x !== point.ebitda_growth_1y || y !== point.ev_ebitda };
  });
  const self = dots.filter((dot) => dot.is_self);
  const near = dots.filter((dot) => !dot.is_self && peerSet.has(dot.ticker));
  const rest = dots.filter((dot) => !dot.is_self && !peerSet.has(dot.ticker));
  const clipped = dots.filter((dot) => dot.clipped).length;

  return (
    <div>
      <div
        className="h-[300px] w-full"
        aria-label="EV/EBITDA against EBITDA growth for the sector, peers highlighted"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
            <XAxis
              type="number"
              dataKey="x"
              domain={GROWTH_RANGE}
              tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              name="EBITDA 1y"
            />
            <YAxis
              type="number"
              dataKey="y"
              scale="log"
              domain={MULTIPLE_RANGE}
              ticks={[2, 5, 10, 20, 50, 100]}
              tickFormatter={(value: number) => `${value}x`}
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              width={40}
              name="EV/EBITDA"
            />
            <ZAxis range={[36, 36]} />
            {medianGrowth != null ? (
              <ReferenceLine x={clamp(medianGrowth, GROWTH_RANGE)} stroke="#384152" strokeDasharray="3 3" />
            ) : null}
            {medianMultiple != null ? (
              <ReferenceLine y={clamp(medianMultiple, MULTIPLE_RANGE)} stroke="#384152" strokeDasharray="3 3" />
            ) : null}
            <Tooltip cursor={false} content={<DotTip />} />
            <Scatter data={rest} fill={SECTOR_COLOR} fillOpacity={0.55} isAnimationActive={false} />
            <Scatter
              data={near}
              fill={PEER_COLOR}
              stroke="#0a0e14"
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Scatter
              data={self}
              fill={SELF_COLOR}
              stroke="#0a0e14"
              strokeWidth={2}
              shape={(props: { cx?: number; cy?: number }) => (
                <circle cx={props.cx} cy={props.cy} r={6} fill={SELF_COLOR} stroke="#0a0e14" strokeWidth={2} />
              )}
              isAnimationActive={false}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-mute">
        <Key color={SELF_COLOR} label="This name" />
        <Key color={PEER_COLOR} label="Nearest peers" />
        <Key color={SECTOR_COLOR} label="Rest of sector" />
        <span>Dashed: sector medians · log scale</span>
        {clipped ? <span>{clipped} outside the axes, pinned to the edge</span> : null}
      </div>
    </div>
  );
}

function DotTip({ active, payload }: { active?: boolean; payload?: { payload: Dot }[] }) {
  const dot = active ? payload?.[0]?.payload : undefined;
  if (!dot) {
    return null;
  }
  return (
    <div className="rounded border border-line bg-panel px-2 py-1 text-[12px]">
      <div className="font-medium text-text-primary">{dot.ticker}</div>
      <div className="tabular-nums text-text-secondary">
        {fmtMultiple(dot.ev_ebitda)} · EBITDA {fmtSignedPct(dot.ebitda_growth_1y)}
      </div>
    </div>
  );
}

function Key({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function clamp(value: number, [lo, hi]: [number, number]): number {
  return Math.min(hi, Math.max(lo, value));
}
