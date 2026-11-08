"use client";

import Link from "next/link";
import { type ReactNode, useMemo, useState } from "react";

import { StaleBadge } from "@/components/StaleBadge";
import { cn } from "@/lib/cn";
import { DASH, fmtUsd, signedClass } from "@/lib/format";
import type { IdeaExclusion, IdeaMember, IdeasTape } from "@/lib/api";

type Tab = "shortlist" | "all" | "excluded";

type SortKey =
  | "rank"
  | "ticker"
  | "sector"
  | "ev_ebitda"
  | "pctile"
  | "fcf_yield"
  | "nd_ebitda"
  | "growth"
  | "mom"
  | "ttm";

type Column = { id: SortKey; label: string; right?: boolean; title?: string };

const RANKED_COLUMNS: Column[] = [
  { id: "rank", label: "#" },
  { id: "ticker", label: "Name" },
  { id: "sector", label: "Sector" },
  { id: "rank", label: "Score", title: "Stacked sleeves, total out of 100" },
  { id: "ev_ebitda", label: "EV/EBITDA", right: true },
  { id: "pctile", label: "5y %ile", right: true, title: "vs own 5y EV/EBITDA; 0 = cheapest" },
  { id: "fcf_yield", label: "FCF yield", right: true },
  {
    id: "nd_ebitda",
    label: "ND/EBITDA",
    right: true,
    title: "Net debt / EBITDA. ( ) = net cash",
  },
  { id: "growth", label: "EBITDA 1y", right: true },
  {
    id: "mom",
    label: "12-1",
    right: true,
    title: "Return over the last 12 months, skipping the most recent one",
  },
];

const EXCLUDED_COLUMNS: Column[] = [
  { id: "ticker", label: "Name" },
  { id: "sector", label: "Sector" },
  { id: "ticker", label: "Why out" },
  { id: "ev_ebitda", label: "EV/EBITDA", right: true },
  { id: "fcf_yield", label: "FCF yield", right: true },
  { id: "growth", label: "EBITDA 1y", right: true },
  { id: "ttm", label: "TTM as of", right: true },
];

// Sleeve order in the stacked bar; risk is subtracted and shown only in the detail.
const SLEEVES = [
  { key: "cheap", label: "Cheap vs own 5y", color: "bg-warning" },
  { key: "quality", label: "Cash quality", color: "bg-accent" },
  { key: "change", label: "EBITDA change", color: "bg-sky-300" },
  { key: "setup", label: "12-1 momentum", color: "bg-slate-500" },
] as const;

const GROWTH_CAP = 9.99;

export function IdeasView({ tape }: { tape: IdeasTape | null }) {
  const [tab, setTab] = useState<Tab>("shortlist");
  const [sector, setSector] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const members = tape?.members ?? [];
  const sectors = useMemo(
    () => Array.from(new Set(members.map((item) => item.sector ?? "Unclassified"))).sort(),
    [members],
  );

  const rows = useMemo(() => {
    let base = members;
    if (tab === "shortlist") {
      base = members.filter((item) => item.status === "ranked").slice(0, tape?.shortlist_n ?? 25);
    } else if (tab === "excluded") {
      base = members.filter((item) => item.status === "excluded");
    }
    if (sector) {
      base = base.filter((item) => (item.sector ?? "Unclassified") === sector);
    }
    const needle = q.trim().toLowerCase();
    if (needle) {
      base = base.filter(
        (item) =>
          item.ticker.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle),
      );
    }
    if (sort) {
      base = [...base].sort((a, b) => compare(a, b, sort.key, sort.desc));
    }
    return base;
  }, [members, tab, sector, q, sort, tape?.shortlist_n]);

  if (tape == null) {
    return <p className="text-sm text-mute">Ideas API unreachable. Start uvicorn, then refresh.</p>;
  }

  const picked =
    members.find((item) => item.ticker === selected) ??
    rows.find((item) => item.status !== "no_score") ??
    null;
  const columns = tab === "excluded" ? EXCLUDED_COLUMNS : RANKED_COLUMNS;
  const ruleLabel = Object.fromEntries(tape.rules.map((rule) => [rule.rule, rule.label]));

  const pickTab = (next: Tab) => {
    setTab(next);
    setSort(null);
  };
  const pickSort = (key: SortKey) => {
    setSort((current) =>
      current?.key === key ? { key, desc: !current.desc } : { key, desc: DESC_FIRST.has(key) },
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-semibold tracking-tight">Ideas</h1>
          <p className="mt-2 text-sm leading-6 text-mute">
            Ranked within each sector: cheap vs own 5y, cash quality, EBITDA change, 12-1
            momentum. Names that fail a data rule are shown with the reason, never ranked. Context
            to study, not a buy signal. Delayed.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.as_of ? <>scores {tape.as_of}</> : "no scores"}
          {tape.stale ? (
            <>
              <span className="mx-2 text-line">·</span>
              <StaleBadge stale />
            </>
          ) : null}
        </p>
      </div>

      {tape.ranked_n === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.compute_scores</code>, then refresh.
        </p>
      ) : (
        <>
          <Kpis tape={tape} />

          {/* "What changed" (top-25 entries / exits, margin turns) lands here in PR 3. */}

          <div className="flex flex-wrap items-center gap-2">
            <TabButton on={tab === "shortlist"} onClick={() => pickTab("shortlist")}>
              Shortlist {tape.shortlist.size}
            </TabButton>
            <TabButton on={tab === "all"} onClick={() => pickTab("all")}>
              All {tape.universe_n}
            </TabButton>
            <TabButton on={tab === "excluded"} onClick={() => pickTab("excluded")}>
              Excluded {tape.excluded_n}
            </TabButton>
            <span className="grow" />
            <select
              aria-label="Sector"
              value={sector}
              onChange={(event) => setSector(event.target.value)}
              className="h-8 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
            >
              <option value="">All sectors</option>
              {sectors.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <input
              aria-label="Search"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="Ticker or name"
              className="h-8 w-40 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
            />
          </div>

          <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <section className="min-w-0 rounded border border-line">
              {tab === "excluded" ? <RuleLegend tape={tape} /> : null}
              <div className="max-h-[75vh] overflow-auto">
                <table className="w-full text-left text-[13px]">
                  <thead className="text-[11px] uppercase tracking-wide text-mute">
                    <tr className="border-b border-line">
                      {columns.map((col) => (
                        <th
                          key={col.label}
                          title={col.title}
                          className={cn(
                            "sticky top-0 z-10 whitespace-nowrap bg-ink px-3 py-2 font-normal",
                            col.right ? "text-right" : "text-left",
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => pickSort(col.id)}
                            className={cn(
                              "uppercase tracking-wide hover:text-white",
                              sort?.key === col.id ? "text-white" : "text-mute",
                            )}
                          >
                            {col.label}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((item) => (
                      <tr
                        key={item.ticker}
                        tabIndex={0}
                        onClick={() => setSelected(item.ticker)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelected(item.ticker);
                          }
                        }}
                        className={cn(
                          "cursor-pointer border-b border-line hover:bg-panel-elevated/60",
                          picked?.ticker === item.ticker && "bg-panel-elevated/80",
                        )}
                      >
                        {tab === "excluded" ? (
                          <ExcludedCells item={item} ruleLabel={ruleLabel} />
                        ) : (
                          <RankedCells item={item} weights={tape.weights} ruleLabel={ruleLabel} />
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {rows.length === 0 ? (
                  <p className="px-3 py-4 text-sm text-mute">No name matches the filter.</p>
                ) : null}
              </div>
            </section>

            <aside className="space-y-4 lg:sticky lg:top-[calc(var(--chrome-h)+1rem)]">
              {picked ? <Detail item={picked} tape={tape} ruleLabel={ruleLabel} /> : null}
              <ScoreLegend weights={tape.weights} />
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

function Kpis({ tape }: { tape: IdeasTape }) {
  const stats = tape.shortlist;
  const [lead, ...rest] = stats.sectors;
  const rules = tape.rules
    .filter((rule) => tape.excluded_by_rule[rule.rule])
    .map((rule) => `${rule.label} ${tape.excluded_by_rule[rule.rule]}`)
    .join(" · ");
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line md:grid-cols-5">
      <Kpi label="In the ranking" value={String(tape.ranked_n)}>
        of {tape.with_data_n} names with comparable data
      </Kpi>
      <Kpi label="Excluded · data rules" value={String(tape.excluded_n)} warn={tape.excluded_n > 0}>
        {rules || "none"}
      </Kpi>
      <Kpi label={`Median EV/EBITDA · top ${stats.size}`} value={multiple(stats.median_ev_ebitda)}>
        {stats.median_pctile_5y == null
          ? "own 5y %ile unavailable"
          : `${stats.median_pctile_5y.toFixed(0)} %ile of own 5y`}
      </Kpi>
      <Kpi label={`Net cash · top ${stats.size}`} value={`${stats.net_cash} / ${stats.size}`}>
        {stats.traps === 0 ? "no value traps" : `${stats.traps} value traps`}
      </Kpi>
      <Kpi
        wide
        label={`Concentration · top ${stats.size}`}
        value={lead ? `${lead.sector} ${lead.count}` : DASH}
      >
        {rest.length
          ? `then ${rest
              .slice(0, 2)
              .map((item) => `${item.sector} ${item.count}`)
              .join(" · ")}`
          : ""}
      </Kpi>
    </div>
  );
}

function Kpi({
  label,
  value,
  warn,
  wide,
  children,
}: {
  label: string;
  value: string;
  warn?: boolean;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1 bg-panel px-3 py-3", wide && "col-span-2 md:col-span-1")}>
      <span className="text-[11px] uppercase tracking-wide text-mute">{label}</span>
      <span className={cn("truncate text-xl tabular-nums", warn && "text-warning")}>{value}</span>
      <span className="text-[12px] leading-5 text-mute">{children}</span>
    </div>
  );
}

function TabButton({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={cn(
        "h-8 rounded border px-3 text-[12px] uppercase tracking-wide tabular-nums",
        on
          ? "border-warning bg-warning text-ink"
          : "border-line bg-panel text-text-secondary hover:border-warning",
      )}
    >
      {children}
    </button>
  );
}

function RankedCells({
  item,
  weights,
  ruleLabel,
}: {
  item: IdeaMember;
  weights: Record<string, number>;
  ruleLabel: Record<string, string>;
}) {
  const score = item.score;
  return (
    <>
      <td className="px-3 py-2 tabular-nums text-mute">{score ? score.rank : DASH}</td>
      <NameCell item={item} />
      <td className="whitespace-nowrap px-3 py-2 text-[12px] text-mute">{item.sector ?? DASH}</td>
      <td className="px-3 py-2">
        {score ? (
          <div className="flex items-center gap-2">
            <ScoreBar item={item} weights={weights} />
            <span className="tabular-nums">{(score.total * 100).toFixed(0)}</span>
          </div>
        ) : (
          <span className="text-[12px] text-mute">
            {item.status === "excluded"
              ? item.exclusions.map((rule) => ruleLabel[rule.rule] ?? rule.rule).join(", ")
              : "no score"}
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{multiple(item.ev_ebitda)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{pctile(item.pctile_5y)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{yieldPct(item.fcf_yield)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{leverage(item.nd_ebitda)}</td>
      <td className={cn("px-3 py-2 text-right tabular-nums", growthClass(item.ebitda_growth_1y))}>
        {growth(item.ebitda_growth_1y)}
      </td>
      <td className={cn("px-3 py-2 text-right tabular-nums", signedClass(score?.ret_12_1))}>
        {momentum(score?.ret_12_1)}
      </td>
    </>
  );
}

function ExcludedCells({
  item,
  ruleLabel,
}: {
  item: IdeaMember;
  ruleLabel: Record<string, string>;
}) {
  return (
    <>
      <NameCell item={item} />
      <td className="whitespace-nowrap px-3 py-2 text-[12px] text-mute">{item.sector ?? DASH}</td>
      <td className="min-w-[16rem] px-3 py-2 text-[12px] leading-5">
        {item.exclusions.map((rule) => (
          <div key={rule.rule}>
            <RuleChip>{ruleLabel[rule.rule] ?? rule.rule}</RuleChip>
            <span className="text-mute">{ruleText(rule)}</span>
          </div>
        ))}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{multiple(item.ev_ebitda)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{yieldPct(item.fcf_yield)}</td>
      <td className={cn("px-3 py-2 text-right tabular-nums", growthClass(item.ebitda_growth_1y))}>
        {growth(item.ebitda_growth_1y)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-mute">{item.ttm_as_of ?? DASH}</td>
    </>
  );
}

function NameCell({ item }: { item: IdeaMember }) {
  return (
    <td className="px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <Link
          href={`/t/${encodeURIComponent(item.ticker)}`}
          onClick={(event) => event.stopPropagation()}
          className="font-medium hover:underline"
        >
          {item.ticker}
        </Link>
        {item.score?.trap ? (
          <span className="text-[11px] uppercase tracking-wide text-down">trap</span>
        ) : null}
        {item.accrual === false ? (
          <span className="text-[11px] uppercase tracking-wide text-mute">accr no</span>
        ) : null}
        {item.ttm_source === "yahoo" ? (
          <span className="text-[11px] text-mute" title="Vendor quarters (Yahoo), not SEC">
            *
          </span>
        ) : null}
      </div>
      {item.name && item.name !== item.ticker ? (
        <div className="max-w-[14rem] truncate text-[11px] text-mute">{item.name}</div>
      ) : null}
    </td>
  );
}

function ScoreBar({ item, weights }: { item: IdeaMember; weights: Record<string, number> }) {
  const score = item.score;
  if (!score) {
    return null;
  }
  return (
    <div className="flex h-2 w-28 bg-panel-elevated" aria-hidden>
      {SLEEVES.map((sleeve) => (
        <div
          key={sleeve.key}
          className={sleeve.color}
          style={{ width: `${Math.max(0, (weights[sleeve.key] ?? 0) * score[sleeve.key] * 100)}%` }}
        />
      ))}
    </div>
  );
}

function Detail({
  item,
  tape,
  ruleLabel,
}: {
  item: IdeaMember;
  tape: IdeasTape;
  ruleLabel: Record<string, string>;
}) {
  const score = item.score;
  const meta = [
    item.sector ?? "Unclassified",
    item.ttm_as_of ? `TTM ${item.ttm_as_of}` : null,
    score ? `rank ${score.rank} / ${tape.ranked_n}` : null,
  ].filter(Boolean);
  return (
    <section className="space-y-3 rounded border border-line bg-panel px-4 py-3">
      <div className="flex items-baseline gap-2">
        <span className="text-[11px] uppercase tracking-wide text-warning">Detail</span>
        <span className="text-base font-semibold">{item.ticker}</span>
        <span className="truncate text-[12px] text-mute">{item.name}</span>
        <span className="grow" />
        {score ? <span className="text-xl tabular-nums">{(score.total * 100).toFixed(0)}</span> : null}
      </div>
      <p className="text-[12px] text-mute">{meta.join(" · ")}</p>

      {score ? (
        <div className="space-y-2">
          {SLEEVES.map((sleeve) => (
            <Bar
              key={sleeve.key}
              label={sleeve.label}
              weight={tape.weights[sleeve.key]}
              value={score[sleeve.key]}
              color={sleeve.color}
            />
          ))}
          <Bar label="Risk (subtracted)" weight={tape.weights.risk} value={score.risk} color="bg-down" />
        </div>
      ) : null}

      <div className="space-y-2 border-t border-line pt-3 text-[13px] leading-6">
        {item.status === "excluded" ? (
          <>
            <p className="text-[11px] uppercase tracking-wide text-mute">Out of the ranking</p>
            {item.exclusions.map((rule) => (
              <p key={rule.rule}>
                <RuleChip>{ruleLabel[rule.rule] ?? rule.rule}</RuleChip>
                {ruleText(rule)}
              </p>
            ))}
          </>
        ) : item.status === "no_score" ? (
          <p className="text-mute">
            No score: the EV/EBITDA history is too short for a percentile vs its own 5y, so the
            name is not comparable.
          </p>
        ) : (
          <>
            <p>
              <span className="text-white">Why. </span>
              <span className="text-text-secondary">{item.memo?.why_scored ?? deskWhy(item)}</span>
            </p>
            {item.memo && item.memo.what_10q_changed !== "unavailable" ? (
              <p>
                <span className="text-white">10-Q. </span>
                <span className="text-text-secondary">{item.memo.what_10q_changed}</span>
              </p>
            ) : null}
            {item.memo ? (
              <p>
                <span className="text-white">Invalidation. </span>
                <span className="text-text-secondary">{item.memo.invalidation}</span>
              </p>
            ) : null}
            {item.memo?.caveats ? (
              <p>
                <span className="text-white">Caveats. </span>
                <span className="text-text-secondary">{item.memo.caveats}</span>
              </p>
            ) : null}
            <p className="text-[11px] uppercase tracking-wide text-mute">
              {item.memo ? `memo · ${item.memo.model}` : "desk summary · no memo"}
            </p>
          </>
        )}
      </div>

      <Link
        href={`/t/${encodeURIComponent(item.ticker)}`}
        className="block text-[12px] text-warning hover:underline"
      >
        Open {item.ticker} →
      </Link>
    </section>
  );
}

function Bar({
  label,
  weight,
  value,
  color,
}: {
  label: string;
  weight: number | undefined;
  value: number;
  color: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[12px]">
        <span>
          {label}
          {weight != null ? <span className="text-mute"> · {(weight * 100).toFixed(0)}%</span> : null}
        </span>
        <span className="tabular-nums">{(value * 100).toFixed(0)}</span>
      </div>
      <div className="h-1.5 bg-panel-elevated">
        <div className={cn("h-full", color)} style={{ width: `${Math.min(100, value * 100)}%` }} />
      </div>
    </div>
  );
}

function ScoreLegend({ weights }: { weights: Record<string, number> }) {
  return (
    <section className="space-y-2 rounded border border-line bg-panel px-4 py-3 text-[12px] leading-5">
      <p className="text-[11px] uppercase tracking-wide text-warning">How the score is built</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {SLEEVES.map((sleeve) => (
          <span key={sleeve.key} className="inline-flex items-center gap-1.5">
            <span className={cn("inline-block h-2.5 w-2.5", sleeve.color)} aria-hidden />
            {sleeve.label} {((weights[sleeve.key] ?? 0) * 100).toFixed(0)}%
          </span>
        ))}
      </div>
      <p className="text-mute">
        Each sleeve is a rank within the name&apos;s sector (sectors under 10 names pool with
        the universe). Leverage and value-trap risk subtract up to{" "}
        {((weights.risk ?? 0) * 100).toFixed(0)} points. Insider is held neutral until Form 4.
      </p>
    </section>
  );
}

function RuleLegend({ tape }: { tape: IdeasTape }) {
  return (
    <div className="grid gap-px border-b border-line bg-line sm:grid-cols-2 xl:grid-cols-4">
      {tape.rules.map((rule) => (
        <div key={rule.rule} className="bg-panel px-3 py-2 text-[12px] leading-5">
          <RuleChip>{rule.label}</RuleChip>
          <span className="tabular-nums">{tape.excluded_by_rule[rule.rule] ?? 0}</span>
          <p className="text-mute">{rule.detail}</p>
        </div>
      ))}
    </div>
  );
}

function RuleChip({ children }: { children: ReactNode }) {
  return (
    <span className="mr-1.5 inline-block rounded-sm border border-warning/70 px-1.5 text-[11px] text-warning">
      {children}
    </span>
  );
}

function ruleText(rule: IdeaExclusion): string {
  const v = rule.values;
  switch (rule.rule) {
    case "fcf_one_off":
      if (typeof v.fcf_yield === "number") {
        return `FCF yield ${yieldPct(v.fcf_yield)}.`;
      }
      return `FCF TTM went from ${fmtUsd(numberOr(v.fcf_from))} to ${fmtUsd(numberOr(v.fcf_to))}.`;
    case "base_effect":
      return `EBITDA 1y ${signedPct(numberOr(v.ebitda_growth_1y))}.`;
    case "extreme_multiple":
      return `EV/EBITDA ${multiple(numberOr(v.ev_ebitda))}.`;
    case "stale_ttm":
      return `Latest TTM ${v.ttm_as_of ?? DASH}, ${v.age_days ?? DASH} days old.`;
    default:
      return "";
  }
}

function deskWhy(item: IdeaMember): string {
  const bits: string[] = [];
  if (item.ev_ebitda != null) {
    const vs =
      item.pctile_5y == null ? "own 5y unavailable" : `${pctile(item.pctile_5y)} %ile of own 5y`;
    bits.push(`EV/EBITDA ${multiple(item.ev_ebitda)} (${vs})`);
  }
  if (item.fcf_yield != null) {
    bits.push(`FCF yield ${yieldPct(item.fcf_yield)}`);
  }
  if (item.nd_ebitda != null) {
    bits.push(
      item.nd_ebitda < 0
        ? `net cash ${Math.abs(item.nd_ebitda).toFixed(1)}x EBITDA`
        : `ND/EBITDA ${item.nd_ebitda.toFixed(1)}x`,
    );
  }
  if (item.ebitda_growth_1y != null) {
    bits.push(`EBITDA 1y ${growth(item.ebitda_growth_1y)}`);
  }
  if (item.score?.ret_12_1 != null) {
    bits.push(`12-1 ${momentum(item.score.ret_12_1)}`);
  }
  const trap = item.score?.trap ? " Value trap: cheap with EBITDA falling." : "";
  return `${bits.join(", ")}.${trap}`;
}

// Columns where the first click should put the largest value on top.
const DESC_FIRST = new Set<SortKey>(["fcf_yield", "growth", "mom", "ttm"]);

function sortValue(item: IdeaMember, key: SortKey): number | string | null {
  switch (key) {
    case "rank":
      return item.score?.rank ?? null;
    case "ticker":
      return item.ticker;
    case "sector":
      return item.sector;
    case "ev_ebitda":
      return item.ev_ebitda;
    case "pctile":
      return item.pctile_5y;
    case "fcf_yield":
      return item.fcf_yield;
    case "nd_ebitda":
      return item.nd_ebitda;
    case "growth":
      return item.ebitda_growth_1y;
    case "mom":
      return item.score?.ret_12_1 ?? null;
    case "ttm":
      return item.ttm_as_of;
  }
}

// Blanks always sort last, whichever the direction.
function compare(a: IdeaMember, b: IdeaMember, key: SortKey, desc: boolean): number {
  const left = sortValue(a, key);
  const right = sortValue(b, key);
  if (left == null || right == null) {
    return left == null ? (right == null ? 0 : 1) : -1;
  }
  const order = left < right ? -1 : left > right ? 1 : 0;
  return desc ? -order : order;
}

function numberOr(value: number | string | null | undefined): number | null {
  return typeof value === "number" ? value : null;
}

function multiple(value: number | null): string {
  return value == null ? DASH : `${value.toFixed(1)}x`;
}

function pctile(value: number | null): string {
  return value == null ? DASH : value.toFixed(0);
}

function yieldPct(value: number | null): string {
  return value == null ? DASH : `${(value * 100).toFixed(1)}%`;
}

function leverage(value: number | null): string {
  if (value == null) {
    return DASH;
  }
  return value < 0 ? `(${Math.abs(value).toFixed(1)}x)` : `${value.toFixed(1)}x`;
}

function signedPct(value: number | null): string {
  if (value == null) {
    return DASH;
  }
  const pct = value * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function growth(value: number | null): string {
  if (value != null && Math.abs(value) > GROWTH_CAP) {
    return "n/m";
  }
  return signedPct(value);
}

// 12-1 momentum is stored in percent, not as a fraction.
function momentum(value: number | null | undefined): string {
  if (value == null) {
    return DASH;
  }
  const shown = Math.round(value);
  return `${shown > 0 ? "+" : ""}${shown === 0 ? 0 : shown}%`;
}

function growthClass(value: number | null): string {
  if (value != null && Math.abs(value) > GROWTH_CAP) {
    return "text-mute";
  }
  return signedClass(value);
}
