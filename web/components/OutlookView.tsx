import { cn } from "@/lib/cn";
import type { OutlookEvent, OutlookNews, OutlookSource, OutlookTape } from "@/lib/api";

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

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Outlook</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            Weekday brief is Day 10 (Claude, pack-grounded). News, calendar, and the sources table are
            from Postgres only.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.as_of ? <>as of {tape.as_of}</> : "no pack"}
          {tape.stale ? (
            <>
              <span className="mx-2 text-line">·</span>
              stale
            </>
          ) : null}
        </p>
      </div>

      {tape.brief ? (
        <section className="rounded border border-line bg-panel px-3 py-3 text-sm leading-6">
          {tape.brief}
        </section>
      ) : (
        <p className="text-sm text-mute">
          No generated brief yet. Run <code className="text-white">python -m jobs.build_pack</code> so
          Day 10 has evidence. Sources below are live counts.
        </p>
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="space-y-4">
          <h2 className="text-[11px] uppercase tracking-wide text-mute">News tape</h2>
          {tape.news.length === 0 ? (
            <p className="text-sm text-mute">
              Run <code className="text-white">python -m jobs.ingest_news</code>.
            </p>
          ) : (
            [...grouped.entries()].map(([category, items]) => (
              <div key={category} className="overflow-hidden rounded border border-line">
                <h3 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
                  {category.replaceAll("_", " ")}
                </h3>
                {items.map((item, index) => (
                  <NewsRow key={`${item.url}-${index}`} item={item} last={index === items.length - 1} />
                ))}
              </div>
            ))
          )}
        </section>

        <aside className="space-y-6">
          <section className="overflow-hidden rounded border border-line">
            <h2 className="border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
              Calendar
            </h2>
            {tape.events.length === 0 ? (
              <p className="px-3 py-3 text-sm text-mute">
                Run <code className="text-white">python -m jobs.ingest_calendar</code>.
              </p>
            ) : (
              tape.events.map((item, index) => (
                <EventRow
                  key={`${item.source}-${item.date}-${item.title}`}
                  item={item}
                  last={index === tape.events.length - 1}
                />
              ))
            )}
          </section>
        </aside>
      </div>

      <SourcesTable rows={tape.sources} />
    </div>
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
          {item.kind}
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
