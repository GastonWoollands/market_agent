"use client";

import { Fragment, useState } from "react";

import { StaleBadge } from "@/components/StaleBadge";
import { cn } from "@/lib/cn";
import type {
  OutlookEvent,
  OutlookJudgment,
  OutlookMacro,
  OutlookNews,
  OutlookOdds,
  OutlookSource,
  OutlookPolicyItem,
  OutlookTape,
  OutlookWatch,
  OutlookWatchScenario,
  OutlookCalendarItem,
} from "@/lib/api";

export function OutlookView({ tape }: { tape: OutlookTape | null }) {
  if (tape == null) {
    return <p className="text-sm text-slate-500">Outlook API unreachable. Start uvicorn, then refresh.</p>;
  }

  const grouped = new Map<string, OutlookNews[]>();
  for (const item of tape.news) {
    const list = grouped.get(item.category) ?? [];
    list.push(item);
    grouped.set(item.category, list);
  }
  const hasBrief = Boolean(tape.abstract || tape.macro_md || tape.brief);
  const spine = (tape.macro_snapshot ?? []).filter((row) => row.spine);
  const restMacro = (tape.macro_snapshot ?? []).filter((row) => !row.spine);
  const headlines = tape.news.slice(0, 5);
  const moreNews = tape.news.slice(5);
  const watch = tape.judgment?.watch?.length ? tape.judgment.watch : [];

  return (
    <div className="max-w-[1400px] mx-auto space-y-10">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">Outlook</h1>
          <StatusChips tape={tape} />
        </div>
      </div>

      {hasBrief ? (
        <Hero tape={tape} />
      ) : (
        <p className="text-sm text-slate-500">
          No generated brief yet. Run{" "}
          <code className="text-slate-200">python -m jobs.generate_outlook --template</code> after{" "}
          <code className="text-slate-200">python -m jobs.build_pack</code>.
        </p>
      )}

      {/* Main content + sidebar grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        {/* Main content - 8 cols */}
        <div className="lg:col-span-8 space-y-10">
          {tape.watch_today && tape.watch_today.length > 0 ? (
            <WatchTodayScenarios scenarios={tape.watch_today} />
          ) : null}

          {(tape.macro_deep || tape.market_deep || tape.policy_deep || tape.geopolitical_deep) ? (
            <DeepDiveTabs
              macro={tape.macro_deep}
              market={tape.market_deep}
              policy={tape.policy_deep}
              geopolitical={tape.geopolitical_deep}
            />
          ) : null}

          {tape.invalidation ? (
            <InvalidationCallout invalidation={tape.invalidation} />
          ) : null}

          {tape.calendar && tape.calendar.length > 0 ? (
            <CalendarTable items={tape.calendar} />
          ) : null}
        </div>

        {/* Sidebar - 4 cols */}
        <aside className="lg:col-span-4 space-y-6">
          <PolicyStrip
            comms={tape.judgment?.policy_comms ?? null}
            items={tape.policy_items ?? []}
          />

          <OddsStrip items={tape.odds ?? []} />

          <TensionList items={tape.judgment?.tensions ?? []} />

          <WatchList items={watch} fallback={tape.events} />
        </aside>
      </div>

      {/* Below the fold - full width */}
      <div className="space-y-8 pt-8 border-t border-slate-800">
        <div className="grid gap-8 lg:grid-cols-2">
          <MacroSnapshot rows={spine.length ? spine : (tape.macro_snapshot ?? [])} title="Spine" />
        </div>

        {tape.macro_md || tape.market_md || tape.near_term_md ? (
          <details className="rounded-lg bg-slate-900/30 px-4 py-3">
            <summary className="cursor-pointer text-[11px] uppercase tracking-widest text-slate-600 font-medium">
              Legacy Expansion
            </summary>
            <div className="mt-4 space-y-4">
              <Section title="Macro" body={tape.macro_md} />
              <Section title="Market" body={tape.market_md} />
              <Section title="Near term" body={tape.near_term_md} />
            </div>
          </details>
        ) : null}

        {restMacro.length > 0 ? (
          <details className="rounded-lg bg-slate-900/30">
            <summary className="cursor-pointer px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
              All series
            </summary>
            <MacroSnapshot rows={restMacro} title="" />
          </details>
        ) : null}

        <details className="rounded-lg bg-slate-900/30 px-4 py-3" open={headlines.length > 0}>
          <summary className="cursor-pointer text-[11px] uppercase tracking-widest text-slate-600 font-medium">
            Headlines
          </summary>
          <div className="mt-4 space-y-4">
            {headlines.length === 0 ? (
              <p className="text-sm text-slate-500">
                Run <code className="text-slate-200">python -m jobs.ingest_news</code>.
              </p>
            ) : (
              [...grouped.entries()].slice(0, 4).map(([category, items]) => (
                <div key={category} className="overflow-hidden rounded-lg border border-slate-800">
                  <h3 className="border-b border-slate-800 bg-slate-900/50 px-4 py-2 text-[11px] uppercase tracking-widest text-slate-600">
                    {category.replaceAll("_", " ")}
                  </h3>
                  {items.slice(0, 2).map((item, index) => (
                    <NewsRow key={`${item.url}-${index}`} item={item} last={index === Math.min(items.length, 2) - 1} />
                  ))}
                </div>
              ))
            )}
            {moreNews.length > 0 ? (
              <p className="text-[11px] text-slate-600">{moreNews.length} more in Postgres.</p>
            ) : null}
          </div>
        </details>

        {(tape.events_later ?? []).length > 0 ? (
          <details className="rounded-lg bg-slate-900/30">
            <summary className="cursor-pointer px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
              Later calendar
            </summary>
            <CalendarBlock title="" items={tape.events_later} empty="" />
          </details>
        ) : null}

        <details className="rounded-lg bg-slate-900/30">
          <summary className="cursor-pointer px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
            Sources
          </summary>
          <SourcesTable rows={tape.sources} />
        </details>
      </div>
    </div>
  );
}

function StatusChips({ tape }: { tape: OutlookTape }) {
  const ten = tape.facts?.dgs10;
  const risk = tape.judgment?.regime?.policy;
  const stance = tape.judgment?.policy_comms?.stance;
  const hold = tape.odds?.find((item) => (item.top_outcome ?? "").toLowerCase().includes("hold"));
  return (
    <div className="flex flex-wrap items-center gap-3 text-[13px] text-slate-500">
      {tape.as_of ? <span className="tabular-nums">{tape.as_of}</span> : <span>no pack</span>}
      {tape.stale ? <StaleBadge stale /> : null}
      {ten != null ? (
        <span className="rounded-md border border-slate-700/50 bg-slate-800/40 px-2.5 py-1 text-[12px] tabular-nums text-slate-300">
          10Y {ten.toFixed(2)}%
        </span>
      ) : null}
      {hold?.top_implied_yes != null ? (
        <span className="rounded-md border border-slate-700/50 bg-slate-800/40 px-2.5 py-1 text-[12px] tabular-nums text-slate-300">
          Hold {formatImplied(hold.top_implied_yes)}
        </span>
      ) : null}
      {stance && stance !== "unavailable" ? (
        <span className="rounded-md border border-slate-700/50 bg-slate-800/40 px-2.5 py-1 text-[12px] text-slate-300">
          {stance}
        </span>
      ) : null}
      {risk ? (
        <span className="rounded-md border border-slate-700/50 bg-slate-800/40 px-2.5 py-1 text-[12px] text-slate-300">
          {risk.replaceAll("_", " ")}
        </span>
      ) : null}
    </div>
  );
}

function Hero({ tape }: { tape: OutlookTape }) {
  const conclusions = tape.conclusions ?? [];
  const lead = tape.tldr || tape.live_md || tape.abstract;
  const hasNewFormat = Boolean(tape.tldr);
  
  return (
    <div className="mb-16">
      {/* Headline */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white tracking-tight mb-2">
          {tape.headline ?? "Outlook"}
        </h2>
      </div>

      {/* TL;DR - hero treatment */}
      {lead ? (
        <div className="bg-slate-800/40 backdrop-blur-sm border border-slate-700/30 rounded-xl px-8 py-6 mb-10">
          <div className="text-[10px] uppercase tracking-widest text-slate-500 font-medium mb-3">
            TL;DR
          </div>
          <p className="text-[17px] leading-[1.7] text-slate-200 font-light">
            {lead}
          </p>
        </div>
      ) : null}
      
      {hasNewFormat && (tape.what_happened || tape.current_positioning || tape.drivers) ? (
        <div className="prose prose-invert max-w-none space-y-8">
          {tape.what_happened ? (
            <section>
              <h3 className="text-[15px] font-semibold text-white mb-3">
                What Happened
              </h3>
              <p className="text-[15px] leading-[1.75] text-slate-400">
                {tape.what_happened}
              </p>
            </section>
          ) : null}
          
          {tape.current_positioning ? (
            <section>
              <h3 className="text-[15px] font-semibold text-white mb-3">
                Current Positioning
              </h3>
              <p className="text-[15px] leading-[1.75] text-slate-400">
                {tape.current_positioning}
              </p>
            </section>
          ) : null}
          
          {tape.drivers ? (
            <section>
              <h3 className="text-[15px] font-semibold text-white mb-3">
                Drivers
              </h3>
              <p className="text-[15px] leading-[1.75] text-slate-400">
                {tape.drivers}
              </p>
            </section>
          ) : null}
        </div>
      ) : (
        <>
          {tape.abstract && tape.abstract !== lead ? (
            <p className="max-w-4xl text-[14px] leading-7 text-slate-400 mb-6">{tape.abstract}</p>
          ) : null}
          {conclusions.length > 0 ? (
            <ul className="max-w-4xl list-disc space-y-2 pl-5 text-[14px] leading-7 text-slate-400">
              {conclusions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}
      
      {tape.expect ? (
        <section className="mt-8 rounded-lg bg-slate-900/30 border border-slate-800 px-6 py-5">
          <p className="text-[11px] uppercase tracking-widest text-slate-600 font-medium mb-3">Expect</p>
          <p className="whitespace-pre-wrap text-[14px] leading-7 text-slate-400">{tape.expect}</p>
        </section>
      ) : null}
    </div>
  );
}

function PolicyStrip({
  comms,
  items,
}: {
  comms: NonNullable<OutlookJudgment["policy_comms"]> | null;
  items: OutlookPolicyItem[];
}) {
  const item = items.find((row) => row.kind === "speech") ?? items[0];
  if (!comms && !item) {
    return null;
  }
  const title = comms?.event || item?.title;
  const kind = comms?.kind || item?.kind;
  const speaker = comms?.speaker || item?.speaker;
  const stance = comms?.stance;
  const published = item?.published_at ? item.published_at.slice(0, 10) : null;
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 px-5 py-4">
      <p className="text-[11px] uppercase tracking-widest text-slate-600 font-medium mb-3">Policy</p>
      <p className="text-[14px] leading-6 text-slate-200 font-medium mb-2">{title}</p>
      <p className="text-[11px] uppercase tracking-wider text-slate-500 mb-3">
        {[kind, speaker, published, stance || null]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {item?.excerpt ? (
        <p className="text-[13px] leading-6 text-slate-500">
          {isVenueExcerpt(item.excerpt) ? `Venue: ${item.excerpt}` : item.excerpt}
        </p>
      ) : null}
      {item?.url ? (
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block text-[12px] text-slate-500 hover:text-slate-300 transition-colors"
        >
          Board source →
        </a>
      ) : null}
    </section>
  );
}

function WatchTodayScenarios({ scenarios }: { scenarios: OutlookWatchScenario[] }) {
  if (scenarios.length === 0) {
    return null;
  }
  
  return (
    <section className="mb-12">
      <h3 className="text-[17px] font-semibold text-white mb-6">
        Watch This Week
      </h3>
      
      <div className="space-y-8">
        {scenarios.map((scenario, index) => (
          <div 
            key={`${scenario.catalyst}-${index}`}
            className={cn(
              "pb-8",
              index < scenarios.length - 1 && "border-b border-slate-800/50"
            )}
          >
            {/* Catalyst header */}
            <div className="flex items-baseline justify-between mb-4">
              <h4 className="text-[15px] font-medium text-slate-200">
                {scenario.catalyst}
              </h4>
              <div className="text-[12px] text-slate-500 tabular-nums">
                {scenario.date && scenario.time ? (
                  <span>{scenario.date} {scenario.time}</span>
                ) : scenario.date ? (
                  <span>{scenario.date}</span>
                ) : scenario.time ? (
                  <span>{scenario.time}</span>
                ) : null}
              </div>
            </div>
            
            {/* Threshold */}
            {scenario.threshold ? (
              <div className="mb-4 text-[13px] text-slate-500">
                Consensus: <span className="text-slate-400 font-medium">{scenario.threshold}</span>
              </div>
            ) : null}
            
            {/* Scenarios - side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Above/Bullish */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 mb-2">
                  <div className="h-px w-8 bg-slate-600" />
                  <p className="text-[11px] uppercase tracking-widest text-slate-500 font-medium">
                    Above consensus
                  </p>
                </div>
                <p className="text-[14px] leading-[1.7] text-slate-400">
                  {scenario.outcome_bullish}
                </p>
              </div>
              
              {/* Below/Bearish */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 mb-2">
                  <div className="h-px w-8 bg-slate-700" />
                  <p className="text-[11px] uppercase tracking-widest text-slate-600 font-medium">
                    Below consensus
                  </p>
                </div>
                <p className="text-[14px] leading-[1.7] text-slate-500">
                  {scenario.outcome_bearish}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function DeepDiveTabs({
  macro,
  market,
  policy,
  geopolitical,
}: {
  macro: string | null;
  market: string | null;
  policy: string | null;
  geopolitical: string | null;
}) {
  const tabs = [
    { id: "macro", label: "Macro", content: macro },
    { id: "markets", label: "Markets", content: market },
    { id: "policy", label: "Policy", content: policy },
    geopolitical ? { id: "geo", label: "Geopolitical", content: geopolitical } : null,
  ].filter((tab): tab is { id: string; label: string; content: string | null } => tab !== null && tab.content !== null);

  const [activeTab, setActiveTab] = useState(tabs[0]?.id ?? "macro");
  const activeContent = tabs.find(tab => tab.id === activeTab)?.content;

  if (tabs.length === 0) {
    return null;
  }

  return (
    <section className="mb-12">
      <h3 className="text-[17px] font-semibold text-white mb-6">
        Deep Dive
      </h3>
      
      {/* Tab navigation */}
      <div className="flex gap-1 mb-6 border-b border-slate-800">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2.5 text-[13px] font-medium transition-colors",
              activeTab === tab.id
                ? "border-b-2 border-slate-300 text-slate-200"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      
      {/* Tab content */}
      <div className="prose prose-invert max-w-none">
        <p className="text-[14px] leading-[1.75] text-slate-400 whitespace-pre-wrap">
          {activeContent}
        </p>
      </div>
    </section>
  );
}

function InvalidationCallout({ invalidation }: { invalidation: string }) {
  return (
    <div className="border-l-4 border-amber-700/50 bg-slate-900/30 pl-6 pr-4 py-5 mb-10 rounded-r-lg">
      <h4 className="text-[12px] uppercase tracking-widest text-amber-600/80 font-medium mb-3">
        Invalidation Triggers
      </h4>
      <p className="text-[14px] leading-relaxed text-slate-400">
        {invalidation}
      </p>
    </div>
  );
}

function TensionList({ items }: { items: NonNullable<OutlookJudgment["tensions"]> }) {
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 overflow-hidden">
      <h2 className="border-b border-slate-800 px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
        Tensions
      </h2>
      {items.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-500">unavailable</p>
      ) : (
        items.map((item, index) => (
          <div
            key={`${item.left}-${item.right}`}
            className={cn("px-4 py-3", index === items.length - 1 ? "" : "border-b border-slate-800")}
          >
            <p className="text-[13px] text-slate-300">
              {item.left}
              <span className="mx-2 text-slate-600">vs</span>
              {item.right}
            </p>
            <p className="text-[11px] uppercase tracking-wider text-slate-600 mt-1">
              {item.note.replaceAll("_", " ")}
            </p>
          </div>
        ))
      )}
    </section>
  );
}

function WatchList({
  items,
  fallback,
}: {
  items: OutlookWatch[];
  fallback: OutlookEvent[];
}) {
  const rows = items.length
    ? items
    : fallback.map((item) => ({
        date: item.date,
        title: item.title,
        kind: item.kind,
        last_print: null,
        why: null,
        role: null,
      }));
  const printed = rows.filter((item) => item.role === "printed");
  const upcoming = rows.filter((item) => item.role !== "printed");
  const grouped = [
    { label: "Printed", items: printed },
    { label: "Next", items: upcoming },
  ].filter((block) => block.items.length > 0);
  
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 overflow-hidden">
      <h2 className="border-b border-slate-800 px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
        Watch
      </h2>
      {grouped.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-500">No upcoming catalysts.</p>
      ) : (
        grouped.map((block, blockIndex) => (
          <div key={block.label}>
            <p className="border-b border-slate-800 bg-slate-900/50 px-4 py-2 text-[11px] uppercase tracking-widest text-slate-600">
              {block.label}
            </p>
            {block.items.map((item, index) => (
              <div
                key={`${item.date}-${item.title}`}
                className={cn(
                  "flex items-baseline gap-3 px-4 py-3",
                  index === block.items.length - 1 && blockIndex === grouped.length - 1
                    ? ""
                    : "border-b border-slate-800",
                )}
              >
                <span className="w-20 shrink-0 text-[12px] tabular-nums text-slate-500">
                  {item.date ? item.date.slice(5) : "—"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] text-slate-300">{item.title}</p>
                  <p className="text-[11px] text-slate-600 mt-0.5">
                    {item.last_print ?? item.kind?.replaceAll("_", " ")}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ))
      )}
    </section>
  );
}

function isVenueExcerpt(text: string): boolean {
  const lower = text.trim().toLowerCase();
  return (
    lower.startsWith("speech at") ||
    lower.startsWith("remarks at") ||
    lower.startsWith("testimony at") ||
    lower.startsWith("statement at")
  );
}

function Section({ title, body }: { title: string; body: string | null }) {
  return (
    <section className="rounded-lg bg-slate-900/50 border border-slate-800 px-5 py-4">
      <p className="text-[11px] uppercase tracking-widest text-slate-600 font-medium mb-3">{title}</p>
      <p className="whitespace-pre-wrap text-[13px] leading-6 text-slate-400">{body || "unavailable"}</p>
    </section>
  );
}

function CalendarTable({ items }: { items: OutlookCalendarItem[] }) {
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 overflow-hidden">
      <h2 className="border-b border-slate-800 px-5 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
        Data Calendar
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-widest text-slate-600">
            <tr className="border-b border-slate-800 bg-slate-900/50">
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Time</th>
              <th className="px-4 py-3 font-medium">Event</th>
              <th className="px-4 py-3 text-right font-medium">Consensus</th>
              <th className="px-4 py-3 text-right font-medium">Prior</th>
              <th className="px-4 py-3 text-right font-medium">Source</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr
                key={`${item.date}-${item.event}-${index}`}
                className={cn(
                  "border-b border-slate-800 last:border-0 hover:bg-slate-900/30 transition-colors",
                )}
              >
                <td className="px-4 py-3 text-slate-500 tabular-nums">{item.date}</td>
                <td className="px-4 py-3 text-slate-500">{item.time || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{item.event}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-400">
                  {item.consensus || "—"}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                  {item.prior || "—"}
                </td>
                <td className="px-4 py-3 text-right text-slate-500">{item.source || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MacroSnapshot({ rows, title = "Spine" }: { rows: OutlookMacro[]; title?: string }) {
  if (rows.length === 0) {
    return (
      <section>
        {title ? <h2 className="mb-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">{title}</h2> : null}
        <p className="text-sm text-slate-500">
          Run <code className="text-slate-200">python -m jobs.build_pack</code>.
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 overflow-hidden">
      {title ? (
        <h2 className="border-b border-slate-800 px-5 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
          {title}
        </h2>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-widest text-slate-600">
            <tr className="border-b border-slate-800 bg-slate-900/50">
              <th className="px-4 py-3 font-medium">Series</th>
              <th className="px-4 py-3 text-right font-medium">Print</th>
              <th className="px-4 py-3 text-right font-medium">Change</th>
              <th className="px-4 py-3 text-right font-medium">As of</th>
            </tr>
          </thead>
          <tbody>
            {groupedSnapshot(rows).map((block) => (
              <Fragment key={block.category}>
                <tr className="border-b border-slate-800 bg-slate-900/50">
                  <td colSpan={4} className="px-4 py-2 text-[11px] uppercase tracking-widest text-slate-600">
                    {block.category.replaceAll("_", " ")}
                  </td>
                </tr>
                {block.rows.map((row) => {
                  const print = snapshotPrint(row);
                  const change = snapshotChange(row);
                  const dim = row.stale || (row.lag_days != null && row.lag_days > 60);
                  return (
                    <tr key={row.series_id} className="border-b border-slate-800 last:border-0 hover:bg-slate-900/30 transition-colors">
                      <td className="px-4 py-3">
                        <span className={dim ? "text-slate-600" : "text-slate-300"}>{row.name ?? row.series_id}</span>
                        <span className="ml-2 text-[11px] uppercase tracking-wider text-slate-600">
                          {row.series_id}
                        </span>
                      </td>
                      <td className={cn("px-4 py-3 text-right tabular-nums", dim ? "text-slate-600" : "text-slate-300")}>
                        {print}
                      </td>
                      <td className={cn("px-4 py-3 text-right tabular-nums", changeClass(change.signed))}>
                        {change.label}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                        {row.as_of ? row.as_of.slice(0, 10) : "—"}
                        {row.lag_days != null ? (
                          <span className="ml-1 text-[11px]">+{row.lag_days}d</span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OddsStrip({ items }: { items: OutlookOdds[] }) {
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 overflow-hidden">
      <h2 className="border-b border-slate-800 px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
        Market-implied
      </h2>
      {items.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-500">No odds in the pack.</p>
      ) : (
        items.map((item, index) => (
          <div
            key={item.slug}
            className={cn(
              "flex items-baseline justify-between gap-3 px-4 py-3",
              index === items.length - 1 ? "" : "border-b border-slate-800",
            )}
          >
            <div className="min-w-0">
              <p className="truncate text-[13px] text-slate-300">{item.label ?? item.slug}</p>
              <p className="truncate text-[11px] text-slate-600 mt-0.5">
                {item.top_outcome
                  ? item.top_outcome
                  : (item.category ?? "odds").replaceAll("_", " ")}
              </p>
            </div>
            <p className="shrink-0 text-[14px] tabular-nums text-slate-300 font-medium">
              {formatImplied(item.top_implied_yes ?? item.implied_yes)}
            </p>
          </div>
        ))
      )}
    </section>
  );
}

function CalendarBlock({
  title,
  items,
  empty,
}: {
  title: string;
  items: OutlookEvent[];
  empty: string;
}) {
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 overflow-hidden">
      <h2 className="border-b border-slate-800 px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
        {title}
      </h2>
      {items.length === 0 ? (
        empty ? <p className="px-4 py-4 text-sm text-slate-500">{empty}</p> : null
      ) : (
        items.map((item, index) => (
          <EventRow
            key={`${item.source}-${item.date}-${item.title}`}
            item={item}
            last={index === items.length - 1}
          />
        ))
      )}
    </section>
  );
}

function NewsRow({ item, last }: { item: OutlookNews; last: boolean }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noreferrer"
      className={cn(
        "block px-4 py-3 hover:bg-slate-900/50 transition-colors",
        last ? "" : "border-b border-slate-800"
      )}
    >
      <p className="text-[13px] leading-5 text-slate-300">{item.title}</p>
      <p className="mt-1.5 text-[11px] text-slate-600">
        {item.publisher}
        <span className="mx-2 text-slate-800">·</span>
        {formatWhen(item.published_at)}
      </p>
    </a>
  );
}

function EventRow({ item, last }: { item: OutlookEvent; last: boolean }) {
  return (
    <div className={cn("flex items-baseline gap-3 px-4 py-3", last ? "" : "border-b border-slate-800")}>
      <span className="w-20 shrink-0 text-[12px] tabular-nums text-slate-500">{item.date.slice(5)}</span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] text-slate-300">{item.title}</p>
        <p className="text-[11px] uppercase tracking-wider text-slate-600 mt-0.5">
          {item.kind.replaceAll("_", " ")}
          {item.ticker ? ` · ${item.ticker}` : ""}
        </p>
      </div>
    </div>
  );
}

function SourcesTable({ rows }: { rows: OutlookSource[] }) {
  return (
    <section className="rounded-lg bg-slate-900/30 border border-slate-800 overflow-hidden">
      <h2 className="border-b border-slate-800 px-4 py-3 text-[11px] uppercase tracking-widest text-slate-600 font-medium">
        Sources
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-widest text-slate-600">
            <tr className="border-b border-slate-800 bg-slate-900/50">
              <th className="px-4 py-3 font-medium">Vendor</th>
              <th className="px-4 py-3 font-medium">Job</th>
              <th className="px-4 py-3 font-medium">As of</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 text-right font-medium">Rows</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.vendor} className="border-b border-slate-800 last:border-0 hover:bg-slate-900/30 transition-colors">
                <td className="px-4 py-3 text-slate-300">{row.vendor}</td>
                <td className="px-4 py-3 text-slate-500">{row.job_name}</td>
                <td className="px-4 py-3 tabular-nums text-slate-500">{formatWhen(row.as_of)}</td>
                <td className={cn("px-4 py-3", row.status === "error" || row.status === "ok" ? statusClass(row.status) : "text-slate-500")}>
                  {row.status ?? "—"}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-300">{row.rows}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const SNAPSHOT_ORDER = [
  "rates",
  "inflation",
  "growth",
  "fiscal",
  "credit",
  "volatility",
  "commodities",
  "fx",
];

function groupedSnapshot(rows: OutlookMacro[]): { category: string; rows: OutlookMacro[] }[] {
  const buckets = new Map<string, OutlookMacro[]>();
  for (const row of rows) {
    const category = row.category || "other";
    const list = buckets.get(category) ?? [];
    list.push(row);
    buckets.set(category, list);
  }
  const seen = new Set<string>();
  const out: { category: string; rows: OutlookMacro[] }[] = [];
  for (const category of SNAPSHOT_ORDER) {
    const list = buckets.get(category);
    if (!list?.length) {
      continue;
    }
    seen.add(category);
    out.push({ category, rows: list });
  }
  for (const [category, list] of buckets) {
    if (!seen.has(category)) {
      out.push({ category, rows: list });
    }
  }
  return out;
}

function snapshotPrint(row: OutlookMacro): string {
  if (row.pack_view === "index_yoy") {
    return row.yoy_pct == null ? "—" : `${row.yoy_pct.toFixed(2)}% YoY`;
  }
  if (row.pack_view === "count_diff") {
    const change = row.print_change ?? row.mom_change;
    return change == null ? "—" : `${formatSigned(change)}${row.unit === "thousands" ? "k" : ""}`;
  }
  if (row.unit === "percent" && row.value != null) {
    return `${row.value.toFixed(2)}%`;
  }
  if (row.value == null) {
    return "—";
  }
  return row.value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function snapshotChange(row: OutlookMacro): { label: string; signed: number | null } {
  if (row.pack_view === "index_yoy") {
    return {
      label: row.mom_pct == null ? "—" : `${formatSigned(row.mom_pct)} MoM`,
      signed: row.mom_pct,
    };
  }
  if (row.pack_view === "yield_bp") {
    return {
      label: row.w1_bp == null ? "—" : `${formatSigned(row.w1_bp, 0)} bp`,
      signed: row.w1_bp,
    };
  }
  if (row.pack_view === "count_diff") {
    return { label: row.change_label ?? "1 print", signed: row.print_change ?? row.mom_change };
  }
  const delta = row.w1 ?? row.d1;
  return { label: delta == null ? "—" : formatSigned(delta), signed: delta };
}

function formatSigned(value: number, digits = 2): string {
  const abs = Math.abs(value).toFixed(digits);
  if (value > 0) {
    return `+${abs}`;
  }
  if (value < 0) {
    return `-${abs}`;
  }
  return abs;
}

function formatImplied(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function changeClass(value: number | null): string {
  if (value == null || value === 0) {
    return "text-slate-600";
  }
  return value > 0 ? "text-up" : "text-down";
}

function statusClass(status: string): string {
  if (status === "ok") {
    return "text-slate-500";
  }
  if (status === "error") {
    return "text-down";
  }
  return "text-slate-500";
}

function formatWhen(value: string | null): string {
  if (!value) {
    return "—";
  }
  if (value.length >= 16 && value.includes("T")) {
    return `${value.slice(0, 10)} ${value.slice(11, 16)}`;
  }
  return value.slice(0, 10);
}
