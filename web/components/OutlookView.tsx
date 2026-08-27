import { Fragment } from "react";

import { StaleBadge } from "@/components/StaleBadge";
import { cn } from "@/lib/cn";
import type {
  OutlookEvent,
  OutlookJudgment,
  OutlookMacro,
  OutlookNews,
  OutlookOdds,
  OutlookSource,
  OutlookTape,
  OutlookWatch,
} from "@/lib/api";

export function OutlookView({ tape }: { tape: OutlookTape | null }) {
  if (tape == null) {
    return <p className="text-sm text-mute">Outlook API unreachable. Start uvicorn, then refresh.</p>;
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
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Outlook</h1>
        <StatusChips tape={tape} />
      </div>

      {hasBrief ? (
        <Hero tape={tape} />
      ) : (
        <p className="text-sm text-mute">
          No generated brief yet. Run{" "}
          <code className="text-white">python -m jobs.generate_outlook --template</code> after{" "}
          <code className="text-white">python -m jobs.build_pack</code>.
        </p>
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <TensionList items={tape.judgment?.tensions ?? []} />
        <WatchList items={watch} fallback={tape.events} />
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <MacroSnapshot rows={spine.length ? spine : (tape.macro_snapshot ?? [])} title="Spine" />
        <OddsStrip items={tape.odds ?? []} />
      </div>

      {tape.macro_md || tape.market_md || tape.near_term_md ? (
        <details className="rounded border border-line bg-panel px-3 py-2">
          <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-mute">
            Expansion
          </summary>
          <div className="mt-3 space-y-3">
            <Section title="Macro" body={tape.macro_md} />
            <Section title="Market" body={tape.market_md} />
            <Section title="Near term" body={tape.near_term_md} />
          </div>
        </details>
      ) : null}

      {restMacro.length > 0 ? (
        <details className="rounded border border-line">
          <summary className="cursor-pointer px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
            All series
          </summary>
          <MacroSnapshot rows={restMacro} title="" />
        </details>
      ) : null}

      <details className="rounded border border-line bg-panel px-3 py-2" open={headlines.length > 0}>
        <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-mute">
          Headlines
        </summary>
        <div className="mt-3 space-y-4">
          {headlines.length === 0 ? (
            <p className="text-sm text-mute">
              Run <code className="text-white">python -m jobs.ingest_news</code>.
            </p>
          ) : (
            [...grouped.entries()].slice(0, 4).map(([category, items]) => (
              <div key={category} className="overflow-hidden rounded border border-line">
                <h3 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
                  {category.replaceAll("_", " ")}
                </h3>
                {items.slice(0, 2).map((item, index) => (
                  <NewsRow key={`${item.url}-${index}`} item={item} last={index === Math.min(items.length, 2) - 1} />
                ))}
              </div>
            ))
          )}
          {moreNews.length > 0 ? (
            <p className="text-[11px] text-mute">{moreNews.length} more in Postgres.</p>
          ) : null}
        </div>
      </details>

      {(tape.events_later ?? []).length > 0 ? (
        <details className="rounded border border-line">
          <summary className="cursor-pointer px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
            Later calendar
          </summary>
          <CalendarBlock title="" items={tape.events_later} empty="" />
        </details>
      ) : null}

      <details className="rounded border border-line">
        <summary className="cursor-pointer px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
          Sources
        </summary>
        <SourcesTable rows={tape.sources} />
      </details>
    </div>
  );
}

function StatusChips({ tape }: { tape: OutlookTape }) {
  const ten = tape.facts?.dgs10;
  const risk = tape.judgment?.regime?.policy;
  const hold = tape.odds?.find((item) => (item.top_outcome ?? "").toLowerCase().includes("hold"));
  return (
    <p className="flex flex-wrap items-center gap-2 text-[13px] text-mute">
      {tape.as_of ? <span>as of {tape.as_of}</span> : <span>no pack</span>}
      {tape.stale ? <StaleBadge stale /> : null}
      {ten != null ? <Chip>{`10Y ${ten.toFixed(2)}%`}</Chip> : null}
      {hold?.top_implied_yes != null ? (
        <Chip>{`Hold ${formatImplied(hold.top_implied_yes)}`}</Chip>
      ) : null}
      {risk ? <Chip>{risk.replaceAll("_", " ")}</Chip> : null}
    </p>
  );
}

function Chip({ children }: { children: string }) {
  return <span className="rounded border border-line px-2 py-0.5 text-[12px] tabular-nums">{children}</span>;
}

function Hero({ tape }: { tape: OutlookTape }) {
  const conclusions = tape.conclusions ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">{tape.headline ?? "Outlook"}</h2>
      <p className="max-w-4xl text-[15px] leading-7">{tape.abstract || tape.brief}</p>
      {conclusions.length > 0 ? (
        <ul className="max-w-4xl list-disc space-y-1 pl-5 text-sm leading-6">
          {conclusions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      {tape.expect ? (
        <section className="rounded border border-line bg-panel px-3 py-3">
          <p className="text-[11px] uppercase tracking-wide text-mute">Expect</p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{tape.expect}</p>
        </section>
      ) : null}
    </div>
  );
}

function TensionList({ items }: { items: NonNullable<OutlookJudgment["tensions"]> }) {
  return (
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        Tensions
      </h2>
      {items.length === 0 ? (
        <p className="px-3 py-3 text-sm text-mute">unavailable</p>
      ) : (
        items.map((item, index) => (
          <div
            key={`${item.left}-${item.right}`}
            className={cn("px-3 py-2", index === items.length - 1 ? "" : "border-b border-line")}
          >
            <p className="text-[13px]">
              {item.left}
              <span className="mx-2 text-mute">vs</span>
              {item.right}
            </p>
            <p className="text-[11px] uppercase tracking-wide text-mute">{item.note.replaceAll("_", " ")}</p>
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
      }));
  return (
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        Watch
      </h2>
      {rows.length === 0 ? (
        <p className="px-3 py-3 text-sm text-mute">No upcoming catalysts.</p>
      ) : (
        rows.map((item, index) => (
          <div
            key={`${item.date}-${item.title}`}
            className={cn("flex items-baseline gap-3 px-3 py-2", index === rows.length - 1 ? "" : "border-b border-line")}
          >
            <span className="w-20 shrink-0 text-[12px] tabular-nums text-mute">
              {item.date ? item.date.slice(5) : "—"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px]">{item.title}</p>
              <p className="text-[11px] text-mute">{item.last_print ?? item.kind?.replaceAll("_", " ")}</p>
            </div>
          </div>
        ))
      )}
    </section>
  );
}

function Section({ title, body }: { title: string; body: string | null }) {
  return (
    <section className="rounded border border-line bg-panel px-3 py-3">
      <p className="text-[11px] uppercase tracking-wide text-mute">{title}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{body || "unavailable"}</p>
    </section>
  );
}

function MacroSnapshot({ rows, title = "Spine" }: { rows: OutlookMacro[]; title?: string }) {
  if (rows.length === 0) {
    return (
      <section>
        {title ? <h2 className="mb-2 text-[11px] uppercase tracking-wide text-mute">{title}</h2> : null}
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.build_pack</code>.
        </p>
      </section>
    );
  }
  return (
    <section className="overflow-hidden rounded border border-line">
      {title ? (
        <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
          {title}
        </h2>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-wide text-mute">
            <tr className="border-b border-line">
              <th className="px-3 py-2 font-normal">Series</th>
              <th className="px-3 py-2 text-right font-normal">Print</th>
              <th className="px-3 py-2 text-right font-normal">Change</th>
              <th className="px-3 py-2 text-right font-normal">As of</th>
            </tr>
          </thead>
          <tbody>
            {groupedSnapshot(rows).map((block) => (
              <Fragment key={block.category}>
                <tr className="border-b border-line bg-white/5">
                  <td colSpan={4} className="px-3 py-1.5 text-[11px] uppercase tracking-wide text-mute">
                    {block.category.replaceAll("_", " ")}
                  </td>
                </tr>
                {block.rows.map((row) => {
                  const print = snapshotPrint(row);
                  const change = snapshotChange(row);
                  const dim = row.stale || (row.lag_days != null && row.lag_days > 60);
                  return (
                    <tr key={row.series_id} className="border-b border-line last:border-0">
                      <td className="px-3 py-2">
                        <span className={dim ? "text-mute" : ""}>{row.name ?? row.series_id}</span>
                        <span className="ml-2 text-[11px] uppercase tracking-wide text-mute">
                          {row.series_id}
                        </span>
                      </td>
                      <td className={cn("px-3 py-2 text-right tabular-nums", dim ? "text-mute" : "")}>
                        {print}
                      </td>
                      <td className={cn("px-3 py-2 text-right tabular-nums", changeClass(change.signed))}>
                        {change.label}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-mute">
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
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        Market-implied
      </h2>
      {items.length === 0 ? (
        <p className="px-3 py-3 text-sm text-mute">No odds in the pack.</p>
      ) : (
        items.map((item, index) => (
          <div
            key={item.slug}
            className={cn(
              "flex items-baseline justify-between gap-3 px-3 py-2",
              index === items.length - 1 ? "" : "border-b border-line",
            )}
          >
            <div className="min-w-0">
              <p className="truncate text-[13px]">{item.label ?? item.slug}</p>
              <p className="truncate text-[11px] text-mute">
                {item.top_outcome
                  ? item.top_outcome
                  : (item.category ?? "odds").replaceAll("_", " ")}
              </p>
            </div>
            <p className="shrink-0 text-sm tabular-nums">
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
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        {title}
      </h2>
      {items.length === 0 ? (
        empty ? <p className="px-3 py-3 text-sm text-mute">{empty}</p> : null
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
      className={cn("block bg-panel px-3 py-2 hover:bg-white/5", last ? "" : "border-b border-line")}
    >
      <p className="text-[13px] leading-5">{item.title}</p>
      <p className="mt-1 text-[11px] text-mute">
        {item.publisher}
        <span className="mx-1.5 text-line">·</span>
        {formatWhen(item.published_at)}
      </p>
    </a>
  );
}

function EventRow({ item, last }: { item: OutlookEvent; last: boolean }) {
  return (
    <div className={cn("flex items-baseline gap-3 px-3 py-2", last ? "" : "border-b border-line")}>
      <span className="w-20 shrink-0 text-[12px] tabular-nums text-mute">{item.date.slice(5)}</span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px]">{item.title}</p>
        <p className="text-[11px] uppercase tracking-wide text-mute">
          {item.kind.replaceAll("_", " ")}
          {item.ticker ? ` · ${item.ticker}` : ""}
        </p>
      </div>
    </div>
  );
}

function SourcesTable({ rows }: { rows: OutlookSource[] }) {
  return (
    <section className="overflow-hidden rounded border border-line">
      <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        Sources
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-wide text-mute">
            <tr className="border-b border-line">
              <th className="px-3 py-2 font-normal">Vendor</th>
              <th className="px-3 py-2 font-normal">Job</th>
              <th className="px-3 py-2 font-normal">As of</th>
              <th className="px-3 py-2 font-normal">Status</th>
              <th className="px-3 py-2 text-right font-normal">Rows</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.vendor} className="border-b border-line last:border-0">
                <td className="px-3 py-2">{row.vendor}</td>
                <td className="px-3 py-2 text-mute">{row.job_name}</td>
                <td className="px-3 py-2 tabular-nums text-mute">{formatWhen(row.as_of)}</td>
                <td className={cn("px-3 py-2", row.status === "error" || row.status === "ok" ? statusClass(row.status) : "text-mute")}>
                  {row.status ?? "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{row.rows}</td>
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
    return "text-mute";
  }
  return value > 0 ? "text-up" : "text-down";
}

function statusClass(status: string): string {
  if (status === "ok") {
    return "text-mute";
  }
  if (status === "error") {
    return "text-down";
  }
  return "text-mute";
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
