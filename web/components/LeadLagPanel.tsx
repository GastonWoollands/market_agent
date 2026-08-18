"use client";

import { useRouter } from "next/navigation";

import { cn } from "@/lib/cn";
import type { DynamicsLagBar, DynamicsLeadLag } from "@/lib/api";
import { pairConclusion, pairHeadline } from "@/lib/dynamics";

type Option = { ticker: string; name: string };

export function LeadLagPanel({
  pair,
  options,
  asOf,
}: {
  pair: DynamicsLeadLag | null;
  options: Option[];
  asOf?: string;
}) {
  const router = useRouter();
  const left = pair?.left ?? options[0]?.ticker ?? "XLK";
  const right = pair?.right ?? options[1]?.ticker ?? "XLF";
  const leftName = options.find((item) => item.ticker === left)?.name ?? left;
  const rightName = options.find((item) => item.ticker === right)?.name ?? right;
  const peakLag = pair?.peak_lag ?? null;
  const peakBar = pair?.bars.find((bar) => bar.lag === peakLag);
  const headline = pairHeadline(peakLag);
  const conclusion = pairConclusion(leftName, rightName, peakLag, peakBar?.corr ?? null);

  function navigate(nextLeft: string, nextRight: string) {
    const query = new URLSearchParams({ lead: nextLeft, lag: nextRight });
    if (asOf) {
      query.set("as_of", asOf);
    }
    router.push(`/dynamics?${query.toString()}`, { scroll: false });
  }

  return (
    <div className="space-y-4">
      <div className="rounded border border-line bg-panel px-3 py-3">
        <p className="text-sm font-medium">{headline}</p>
        <p className="mt-1 text-[12px] leading-5 text-mute">
          Peak |corr| over lags −5 to +5 on overlapping daily closes. Not a trading signal.
        </p>
      </div>

      {options.length > 0 ? (
        <p className="flex flex-wrap items-center gap-2 text-[13px] text-mute">
          <span>Check any pair. Does</span>
          <Select
            name="lead"
            value={left}
            options={options}
            onChange={(ticker) => navigate(ticker, right)}
          />
          <span>move before</span>
          <Select
            name="lag"
            value={right}
            options={options}
            onChange={(ticker) => navigate(left, ticker)}
          />
          <span>?</span>
        </p>
      ) : null}

      {pair ? (
        <LagChart
          bars={pair.bars}
          peak={pair.peak_lag}
          peakCorr={peakBar?.corr ?? null}
          left={left}
          right={right}
        />
      ) : (
        <p className="text-sm text-mute">Pick two sector ETFs with stored closes.</p>
      )}

      <p className="text-[13px] leading-6">{conclusion}</p>
    </div>
  );
}

function Select({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: string;
  options: Option[];
  onChange: (ticker: string) => void;
}) {
  return (
    <select
      name={name}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-8 max-w-[16rem] rounded border border-line bg-ink px-2 text-[13px] text-white outline-none"
    >
      {options.map((item) => (
        <option key={`${name}-${item.ticker}`} value={item.ticker}>
          {item.name} ({item.ticker})
        </option>
      ))}
    </select>
  );
}

function LagChart({
  bars,
  peak,
  peakCorr,
  left,
  right,
}: {
  bars: DynamicsLagBar[];
  peak: number | null;
  peakCorr: number | null;
  left: string;
  right: string;
}) {
  const maxAbs = Math.max(0.2, ...bars.map((bar) => Math.abs(bar.corr ?? 0)));
  const peakIndex = bars.findIndex((bar) => bar.lag === peak);

  return (
    <div>
      <div className="relative h-28">
        {peakIndex >= 0 && peakCorr != null ? (
          <p
            className="absolute -top-0.5 text-[11px] text-[#6cb6ff]"
            style={{
              left: `${((peakIndex + 0.5) / bars.length) * 100}%`,
              transform: "translateX(-50%)",
            }}
          >
            peak {peakCorr.toFixed(2)} at {peak === 0 ? "same day" : `lag ${peak > 0 ? "+" : ""}${peak}`}
          </p>
        ) : null}
        <div className="absolute inset-x-0 bottom-0 flex h-20 items-end gap-1">
          {bars.map((bar) => {
            const height = bar.corr == null ? 0 : (Math.abs(bar.corr) / maxAbs) * 100;
            const isPeak = bar.lag === peak;
            return (
              <div key={bar.lag} className="flex h-full flex-1 flex-col items-center justify-end">
                <div
                  className={cn("w-full max-w-4 rounded-sm", isPeak ? "bg-[#6cb6ff]" : "bg-[#2e2e2e]")}
                  style={{ height: `${height}%` }}
                />
              </div>
            );
          })}
        </div>
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-mute">
        <span>← {right} moves first</span>
        <span>same day</span>
        <span>{left} moves first →</span>
      </div>
    </div>
  );
}
