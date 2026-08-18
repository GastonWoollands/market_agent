"use client";

import type { DynamicsMember } from "@/lib/api";
import { QUADRANT_COLOR, displayName, quadrantLabel } from "@/lib/dynamics";

const VIEW_W = 640;
const VIEW_H = 560;
const PAD = { top: 36, right: 28, bottom: 28, left: 28 };

type Props = {
  members: DynamicsMember[];
  hovered: string | null;
  onHover: (ticker: string | null) => void;
};

export function RrgScatter({ members, hovered, onHover }: Props) {
  if (members.length === 0) {
    return (
      <p className="py-8 text-sm text-mute">
        No rotation points yet. Run <code className="text-white">python -m jobs.compute_dynamics</code>{" "}
        after Yahoo bars are in Postgres.
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
  const pad = Math.max(2, (hi - lo) * 0.14);
  const domain: [number, number] = [lo - pad, hi + pad];
  const plotW = VIEW_W - PAD.left - PAD.right;
  const plotH = VIEW_H - PAD.top - PAD.bottom;
  const xAt = (value: number) => PAD.left + ((value - domain[0]) / (domain[1] - domain[0])) * plotW;
  const yAt = (value: number) => PAD.top + ((domain[1] - value) / (domain[1] - domain[0])) * plotH;
  const originX = xAt(100);
  const originY = yAt(100);
  const ordered = hovered
    ? [...members.filter((item) => item.ticker !== hovered), ...members.filter((item) => item.ticker === hovered)]
    : members;

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      className="h-full w-full"
      role="img"
      aria-label="Sector rotation versus the S&P 500"
      onMouseLeave={() => onHover(null)}
    >
      <line x1={originX} y1={PAD.top} x2={originX} y2={PAD.top + plotH} stroke="#2a2a2a" strokeWidth="1" />
      <line x1={PAD.left} y1={originY} x2={PAD.left + plotW} y2={originY} stroke="#2a2a2a" strokeWidth="1" />

      <CornerLabel
        x={PAD.left + 8}
        y={PAD.top + 16}
        title="IMPROVING"
        hint="weak, turning up"
        color={QUADRANT_COLOR.improving}
        anchor="start"
      />
      <CornerLabel
        x={PAD.left + plotW - 8}
        y={PAD.top + 16}
        title="LEADING"
        hint="strong, still gaining"
        color={QUADRANT_COLOR.leading}
        anchor="end"
      />
      <CornerLabel
        x={PAD.left + 8}
        y={PAD.top + plotH - 28}
        title="LAGGING"
        hint="weak, still falling"
        color={QUADRANT_COLOR.lagging}
        anchor="start"
      />
      <CornerLabel
        x={PAD.left + plotW - 8}
        y={PAD.top + plotH - 28}
        title="WEAKENING"
        hint="strong, but fading"
        color={QUADRANT_COLOR.weakening}
        anchor="end"
      />

      {members.map((item) =>
        item.trail.length > 1 ? (
          <polyline
            key={`${item.ticker}-trail`}
            fill="none"
            stroke={QUADRANT_COLOR[item.quadrant] ?? "#8a8a8a"}
            strokeWidth={hovered === item.ticker ? 1.75 : 1.15}
            strokeOpacity={hovered == null || hovered === item.ticker ? 0.45 : 0.12}
            points={item.trail.map((point) => `${xAt(point.rs_ratio)},${yAt(point.rs_momentum)}`).join(" ")}
          />
        ) : null,
      )}

      {ordered.map((item) => {
        const cx = xAt(item.rs_ratio);
        const cy = yAt(item.rs_momentum);
        const color = QUADRANT_COLOR[item.quadrant] ?? "#ececec";
        const active = hovered === item.ticker;
        const dim = hovered != null && !active;
        return (
          <g
            key={item.ticker}
            opacity={dim ? 0.28 : 1}
            onMouseEnter={() => onHover(item.ticker)}
            style={{ cursor: "default" }}
          >
            <title>
              {`${displayName(item)} (${item.ticker}) · ${quadrantLabel(item.quadrant)}`}
            </title>
            <circle cx={cx} cy={cy} r="11" fill="transparent" />
            <circle cx={cx} cy={cy} r={active ? 6 : 4.5} fill={color} />
            <text
              x={cx + 8}
              y={cy + 3}
              fill={active ? "#ececec" : "#8a8a8a"}
              fontSize="10"
              fontWeight={active ? 600 : 400}
            >
              {item.ticker}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function CornerLabel({
  x,
  y,
  title,
  hint,
  color,
  anchor,
}: {
  x: number;
  y: number;
  title: string;
  hint: string;
  color: string;
  anchor: "start" | "end";
}) {
  return (
    <text x={x} y={y} textAnchor={anchor}>
      <tspan fill={color} fontSize="10" letterSpacing="0.08em">
        {title}
      </tspan>
      <tspan x={x} dy="13" fill="#8a8a8a" fontSize="10" letterSpacing="0">
        {hint}
      </tspan>
    </text>
  );
}
