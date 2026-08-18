"use client";

import { useState } from "react";

import type { DynamicsCorr } from "@/lib/api";
import { averageCorr, corrPairs } from "@/lib/dynamics";

export function CorrHeatmap({
  corr,
  names,
}: {
  corr: DynamicsCorr | null;
  names: Record<string, string>;
}) {
  const [hover, setHover] = useState<string | null>(null);
  if (corr == null || corr.tickers.length < 2) {
    return <p className="text-sm text-mute">Not enough overlapping sector bars for a matrix.</p>;
  }

  const tickers = corr.tickers;
  const pairs = corrPairs(corr);
  const tightest = [...pairs].sort((a, b) => b.value - a.value).slice(0, 3);
  const diversifiers = [...pairs]
    .filter((pair) => pair.value < 0)
    .sort((a, b) => a.value - b.value)
    .slice(0, 3);
  const average = averageCorr(pairs);
  const label = (ticker: string) => names[ticker] ?? ticker;
  const pairLabel = (left: string, right: string, value: number) =>
    `${label(left)} & ${label(right)} ${value.toFixed(2)}`;

  const size = tickers.length - 1;

  return (
    <div>
      <div className="overflow-x-auto" onMouseLeave={() => setHover(null)}>
        <div
          className="inline-grid gap-1 text-[10px]"
          style={{ gridTemplateColumns: `auto repeat(${size}, 1.75rem)` }}
        >
          <div />
          {tickers.slice(0, -1).map((ticker) => (
            <div key={`col-${ticker}`} className="text-center font-normal leading-4 text-mute">
              {ticker}
            </div>
          ))}
          {tickers.slice(1).map((rowTicker, rowOffset) => {
            const i = rowOffset + 1;
            return (
              <div key={`row-${rowTicker}`} className="contents">
                <div className="pr-2 text-left leading-7 text-mute">{rowTicker}</div>
                {tickers.slice(0, -1).map((colTicker, j) => {
                  if (j >= i) {
                    return <div key={`${rowTicker}-${colTicker}`} />;
                  }
                  const value = corr.matrix[i]?.[j];
                  const text =
                    value == null
                      ? `${label(colTicker)} & ${label(rowTicker)} n/a`
                      : pairLabel(colTicker, rowTicker, value);
                  return (
                    <div
                      key={`${rowTicker}-${colTicker}`}
                      role="presentation"
                      className="h-7 w-7 cursor-crosshair rounded-sm"
                      style={{ background: corrFill(value) }}
                      title={text}
                      onMouseEnter={() => setHover(text)}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-mute">{hover ?? "Hover a cell for the pair and its number."}</p>
      <div className="mt-4 flex items-center gap-3 text-[11px] text-mute">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: corrFill(-0.8) }} />
          move opposite
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: corrFill(0.8) }} />
          move together
        </span>
      </div>
      {tightest.length > 0 ? (
        <p className="mt-4 text-[13px] leading-6">
          <span className="text-mute">Tightest pairs </span>
          {tightest.map((pair) => pairLabel(pair.left, pair.right, pair.value)).join(" · ")}
        </p>
      ) : null}
      {diversifiers.length > 0 ? (
        <p className="text-[13px] leading-6">
          <span className="text-mute">Best diversifiers </span>
          {diversifiers.map((pair) => pairLabel(pair.left, pair.right, pair.value)).join(" · ")}
        </p>
      ) : null}
      {average != null ? (
        <p className="mt-2 text-[13px] text-mute">
          Average pair correlation {average.toFixed(2)} · {corr.window} sessions of overlapping daily
          closes.
        </p>
      ) : null}
    </div>
  );
}

function corrFill(value: number | null): string {
  if (value == null) {
    return "#1a1a1a";
  }
  const alpha = 0.12 + Math.min(1, Math.abs(value)) * 0.72;
  if (value >= 0) {
    return `rgba(56, 97, 251, ${alpha})`;
  }
  return `rgba(232, 140, 48, ${alpha})`;
}
