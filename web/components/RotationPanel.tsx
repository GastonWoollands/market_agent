"use client";

import { useState } from "react";

import { RrgScatter } from "@/components/RrgScatter";
import { cn } from "@/lib/cn";
import type { DynamicsMember } from "@/lib/api";
import {
  QUADRANTS,
  QUADRANT_COLOR,
  QUADRANT_DOT,
  QUADRANT_TEXT,
  displayName,
  formatSigned,
  priorQuadrant,
  quadrantLabel,
} from "@/lib/dynamics";

export function RotationPanel({
  members,
  benchmark,
}: {
  members: DynamicsMember[];
  benchmark: string;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const maxAbs = Math.max(3, ...members.map((item) => Math.abs(item.rs_ratio - 100)));
  const grouped = QUADRANTS.map((quadrant) => ({
    ...quadrant,
    items: members.filter((item) => item.quadrant === quadrant.id),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <div>
        <div className="h-[28rem] w-full lg:h-[32rem]">
          <RrgScatter members={members} hovered={hovered} onHover={setHovered} />
        </div>
        <p className="mt-1 text-center text-[11px] text-mute">
          ← weaker than {benchmark} · stronger than {benchmark} →
        </p>
      </div>
      <div>
        <div className="space-y-4">
          {grouped.map((group) => (
            <div key={group.id}>
              <p className="mb-1.5 flex items-center gap-2 text-[11px] uppercase tracking-wide text-mute">
                <span className={cn("h-1.5 w-1.5 rounded-full", QUADRANT_DOT[group.id])} />
                {group.label}
              </p>
              {group.items.map((item) => (
                <MemberRow
                  key={item.ticker}
                  item={item}
                  maxAbs={maxAbs}
                  active={hovered === item.ticker}
                  dim={hovered != null && hovered !== item.ticker}
                  onHover={setHovered}
                />
              ))}
            </div>
          ))}
        </div>
        <p className="mt-4 text-[11px] leading-5 text-mute">
          Bar: distance from the {benchmark} trend (right of the tick = stronger). Last column:
          quadrant three weeks ago.
        </p>
      </div>
    </div>
  );
}

function MemberRow({
  item,
  maxAbs,
  active,
  dim,
  onHover,
}: {
  item: DynamicsMember;
  maxAbs: number;
  active: boolean;
  dim: boolean;
  onHover: (ticker: string | null) => void;
}) {
  const delta = item.rs_ratio - 100;
  const prior = priorQuadrant(item);
  const priorSame = prior == null || prior === item.quadrant;
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded px-1 py-1.5 transition-opacity",
        active ? "bg-panel" : "",
        dim ? "opacity-40" : "",
      )}
      onMouseEnter={() => onHover(item.ticker)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] leading-4">{displayName(item)}</p>
        <p className="text-[11px] text-mute">{item.ticker}</p>
      </div>
      <StrengthBar value={delta} maxAbs={maxAbs} color={QUADRANT_COLOR[item.quadrant] ?? "#8a8a8a"} />
      <span className={cn("w-9 text-right text-[13px] tabular-nums", QUADRANT_TEXT[item.quadrant])}>
        {formatSigned(delta)}
      </span>
      <span
        className={cn(
          "w-[5.75rem] text-right text-[11px]",
          priorSame ? "text-mute" : QUADRANT_TEXT[prior ?? ""],
        )}
      >
        {prior == null ? "—" : priorSame ? "steady" : `was ${quadrantLabel(prior)}`}
      </span>
    </div>
  );
}

function StrengthBar({
  value,
  maxAbs,
  color,
}: {
  value: number;
  maxAbs: number;
  color: string;
}) {
  const span = Math.max(maxAbs, 1);
  const ratio = Math.max(-1, Math.min(1, value / span));
  const mid = 36;
  const width = Math.abs(ratio) * mid;
  return (
    <svg width="72" height="12" className="shrink-0" aria-hidden>
      <line x1={mid} y1="2" x2={mid} y2="10" stroke="#3a3a3a" strokeWidth="1" />
      {width > 0 ? (
        <rect
          x={ratio >= 0 ? mid : mid - width}
          y="4"
          width={width}
          height="4"
          rx="1"
          fill={color}
        />
      ) : null}
    </svg>
  );
}
