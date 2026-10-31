"use client";

import Link from "next/link";
import { useState } from "react";

import { StaleBadge } from "@/components/StaleBadge";
import { cn } from "@/lib/cn";
import type { OpportunityMember, OpportunityTape } from "@/lib/api";

const GROWTH_CAP = 9.99;

const SORTS = [
  { id: "rank", label: "#", align: "left" as const },
  { id: "ticker", label: "Ticker", align: "left" as const },
  { id: "ev_ebitda", label: "EV/EBITDA", align: "right" as const },
  {
    id: "pctile",
    label: "5y %ile",
    align: "right" as const,
    title: "vs own 5y EV/EBITDA; 0 = cheapest",
  },
  { id: "fcf_yield", label: "FCF yield", align: "right" as const },
  {
    id: "nd_ebitda",
    label: "ND/EBITDA",
    align: "right" as const,
    title: "Net debt / EBITDA. Negative or ( ) = net cash",
  },
  { id: "growth", label: "EBITDA 1y", align: "right" as const },
];

export function OpportunitiesView({
  tape,
  query,
}: {
  tape: OpportunityTape | null;
  query: { sort: string; asOf: string };
}) {
  const [selected, setSelected] = useState<string | null>(null);

  if (tape == null) {
    return (
      <p className="text-sm text-mute">Opportunities API unreachable. Start uvicorn, then refresh.</p>
    );
  }

  const sort = query.sort || tape.sort || "rank";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Opportunities</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            Cheap vs own history, cash, leverage, and growth. Delayed. Not advice.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.count} names
          {tape.as_of ? (
            <>
              <span className="mx-2 text-line">·</span>
              as of {tape.as_of}
            </>
          ) : null}
          {tape.stale ? (
            <>
              <span className="mx-2 text-line">·</span>
              <StaleBadge stale />
            </>
          ) : null}
        </p>
      </div>

      {tape.members.length === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.compute_scores</code>, then{" "}
          <code className="text-white">python -m jobs.generate_memos --template</code>.
        </p>
      ) : (
        <section className="rounded border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wide text-mute">
              <tr className="border-b border-line">
                {SORTS.map((col) => (
                  <th
                    key={col.id}
                    className={cn(
                      "sticky top-12 z-10 bg-ink px-3 py-2 font-normal",
                      col.align === "right" ? "text-right" : "text-left",
                    )}
                    title={col.title}
                  >
                    <Link
                      href={sortHref(col.id, query.asOf)}
                      className={cn(
                        "hover:text-white",
                        sort === col.id ? "text-white" : "text-mute",
                      )}
                    >
                      {col.label}
                    </Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tape.members.map((row) => (
                <MemberBlock
                  key={row.ticker}
                  item={row}
                  open={selected === row.ticker}
                  onToggle={() =>
                    setSelected((current) => (current === row.ticker ? null : row.ticker))
                  }
                />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function MemberBlock({
  item,
  open,
  onToggle,
}: {
  item: OpportunityMember;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        className={cn(
          "cursor-pointer border-b border-line hover:bg-panel-elevated/60",
          open ? "bg-panel-elevated/80" : "",
        )}
        onClick={onToggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onToggle();
          }
        }}
        tabIndex={0}
      >
        <td className="px-3 py-2 tabular-nums text-mute">{item.rank}</td>
        <td className="px-3 py-2">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <Link
              href={`/t/${encodeURIComponent(item.ticker)}`}
              onClick={(event) => event.stopPropagation()}
              className="font-medium hover:underline"
            >
              {item.ticker}
            </Link>
            {item.trap ? <span className="text-[11px] uppercase tracking-wide text-down">trap</span> : null}
            {item.accrual === false ? (
              <span className="text-[11px] uppercase tracking-wide text-mute">accr no</span>
            ) : null}
          </div>
          {item.name && item.name !== item.ticker ? (
            <div className="max-w-[14rem] truncate text-[11px] text-mute">{item.name}</div>
          ) : null}
        </td>
        <td className="px-3 py-2 text-right tabular-nums">{formatMultiple(item.ev_ebitda)}</td>
        <td
          className="px-3 py-2 text-right tabular-nums"
          title="vs own 5y EV/EBITDA; 0 = cheapest"
        >
          {formatPctile(item.pctile_5y)}
        </td>
        <td className="px-3 py-2 text-right tabular-nums">{formatYield(item.fcf_yield)}</td>
        <td
          className="px-3 py-2 text-right tabular-nums"
          title={ndTitle(item.nd_ebitda)}
        >
          {formatLeverage(item.nd_ebitda)}
        </td>
        <td className={cn("px-3 py-2 text-right tabular-nums", growthClass(item.ebitda_growth_1y))}>
          {formatGrowth(item.ebitda_growth_1y)}
        </td>
      </tr>
      {open ? (
        <tr className="border-b border-line bg-panel/40">
          <td colSpan={7} className="px-3 py-3 text-[13px] leading-6 text-mute">
            <p>
              <span className="text-white">Why. </span>
              {item.memo?.why_scored ?? deskWhy(item)}
            </p>
            {item.memo && item.memo.what_10q_changed !== "unavailable" ? (
              <p className="mt-2">
                <span className="text-white">10-Q. </span>
                {item.memo.what_10q_changed}
              </p>
            ) : null}
            <p className="mt-2">
              <span className="text-white">Invalidation. </span>
              {item.memo?.invalidation ?? deskInvalidation(item)}
            </p>
            {item.memo?.caveats ? (
              <p className="mt-2">
                <span className="text-white">Caveats. </span>
                {item.memo.caveats}
              </p>
            ) : null}
            <p className="mt-2 text-[11px] uppercase tracking-wide">
              {item.memo ? `memo · ${item.memo.model}` : "desk summary · no memo"}
            </p>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function sortHref(sort: string, asOf: string): string {
  const params = new URLSearchParams();
  params.set("sort", sort);
  if (asOf) {
    params.set("as_of", asOf);
  }
  return `/opportunities?${params.toString()}`;
}

function deskWhy(item: OpportunityMember): string {
  const bits: string[] = [];
  if (item.ev_ebitda != null) {
    const vs =
      item.pctile_5y == null
        ? "vs own 5y unavailable"
        : `${ordinal(item.pctile_5y)} %ile vs own 5y`;
    bits.push(`EV/EBITDA ${item.ev_ebitda.toFixed(1)} (${vs})`);
  }
  if (item.fcf_yield != null) {
    bits.push(`FCF yield ${(item.fcf_yield * 100).toFixed(1)}%`);
  }
  if (item.nd_ebitda != null) {
    bits.push(
      item.nd_ebitda < 0
        ? `net cash ${Math.abs(item.nd_ebitda).toFixed(1)}x EBITDA`
        : `ND/EBITDA ${item.nd_ebitda.toFixed(1)}x`,
    );
  }
  if (item.ebitda_growth_1y != null) {
    bits.push(`EBITDA 1y ${formatGrowth(item.ebitda_growth_1y)}`);
  }
  const flags: string[] = [];
  if (item.trap) {
    flags.push("trap");
  }
  if (item.accrual === false) {
    flags.push("accrual no");
  }
  const body = bits.join(", ");
  const flagText = flags.length ? ` ${flags.join(", ")}.` : "";
  return `${item.ticker}${body ? ` ${body}.` : "."}${flagText} Delayed. Not advice.`;
}

function deskInvalidation(item: OpportunityMember): string {
  const growth =
    item.ebitda_growth_1y == null ? "unavailable" : formatGrowth(item.ebitda_growth_1y);
  return `EV/EBITDA mean-reverts toward its 5y history or EBITDA growth ${growth} fades.`;
}

function ordinal(value: number): string {
  const n = Math.round(value);
  const mod = n % 100;
  if (mod >= 11 && mod <= 13) {
    return `${n}th`;
  }
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

function extremeGrowth(value: number | null): boolean {
  return value != null && Math.abs(value) > GROWTH_CAP;
}

function growthClass(value: number | null): string {
  if (value == null || value === 0 || extremeGrowth(value)) {
    return "text-mute";
  }
  return value > 0 ? "text-up" : "text-down";
}

function formatMultiple(value: number | null): string {
  if (value == null) {
    return "—";
  }
  return value.toFixed(1);
}

function formatPctile(value: number | null): string {
  if (value == null) {
    return "—";
  }
  return `${value.toFixed(0)}`;
}

function formatYield(value: number | null): string {
  if (value == null) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatLeverage(value: number | null): string {
  if (value == null) {
    return "—";
  }
  if (value < 0) {
    return `(${Math.abs(value).toFixed(1)}x)`;
  }
  return `${value.toFixed(1)}x`;
}

function ndTitle(value: number | null): string {
  if (value == null) {
    return "Net debt / EBITDA unavailable";
  }
  if (value < 0) {
    return "Net cash (ND/EBITDA)";
  }
  return "Net debt / EBITDA";
}

function formatGrowth(value: number | null): string {
  if (value == null) {
    return "—";
  }
  if (extremeGrowth(value)) {
    return "n/m";
  }
  const pct = value * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}
