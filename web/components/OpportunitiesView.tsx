import { StaleBadge } from "@/components/StaleBadge";
import { cn } from "@/lib/cn";
import type { OpportunityMember, OpportunityTape } from "@/lib/api";

const SORTS = [
  { id: "rank", label: "Rank" },
  { id: "total", label: "Total" },
  { id: "cheap", label: "Cheap" },
  { id: "quality", label: "Quality" },
  { id: "change", label: "Change" },
  { id: "setup", label: "Setup" },
] as const;

export function OpportunitiesView({
  tape,
  query,
}: {
  tape: OpportunityTape | null;
  query: { sort: string; asOf: string };
}) {
  if (tape == null) {
    return (
      <p className="text-sm text-mute">Opportunities API unreachable. Start uvicorn, then refresh.</p>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Opportunities</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            Quant sleeves first from stored EV/EBITDA, FCF margin, 1y EBITDA growth, and 63-session
            returns. Memos cover rank ≤ 20 and may only narrate those fields. Insider is 0.5 until
            Form 4 exists.
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

      <form method="get" action="/opportunities" className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] uppercase tracking-wide text-mute">
          Sort
          <select
            name="sort"
            defaultValue={query.sort || tape.sort}
            className="mt-1 block h-8 w-40 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
          >
            {SORTS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="h-8 rounded border border-line bg-panel px-3 text-[13px] text-white"
        >
          Apply
        </button>
      </form>

      {tape.members.length === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.compute_scores</code>, then{" "}
          <code className="text-white">python -m jobs.generate_memos --template</code>.
        </p>
      ) : (
        <section className="overflow-hidden rounded border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wide text-mute">
              <tr className="border-b border-line">
                <th className="px-3 py-2 font-normal">#</th>
                <th className="px-3 py-2 font-normal">Ticker</th>
                <th className="px-3 py-2 text-right font-normal">Total</th>
                <th className="px-3 py-2 text-right font-normal">Cheap</th>
                <th className="px-3 py-2 text-right font-normal">Quality</th>
                <th className="px-3 py-2 text-right font-normal">Change</th>
                <th className="px-3 py-2 text-right font-normal">Setup</th>
                <th className="px-3 py-2 text-right font-normal">Risk</th>
                <th className="px-3 py-2 text-right font-normal">EBITDA 1y</th>
              </tr>
            </thead>
            <tbody>
              {tape.members.map((row) => (
                <MemberBlock key={row.ticker} item={row} />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function MemberBlock({ item }: { item: OpportunityMember }) {
  return (
    <>
      <tr className="border-b border-line">
        <td className="px-3 py-2 tabular-nums text-mute">{item.rank}</td>
        <td className="px-3 py-2 font-medium">
          {item.ticker}
          {item.trap ? <span className="ml-2 text-[11px] text-down">trap</span> : null}
        </td>
        <td className="px-3 py-2 text-right tabular-nums">{item.total.toFixed(2)}</td>
        <td className="px-3 py-2 text-right tabular-nums">{item.cheap.toFixed(2)}</td>
        <td className="px-3 py-2 text-right tabular-nums">{item.quality.toFixed(2)}</td>
        <td className="px-3 py-2 text-right tabular-nums">{item.change.toFixed(2)}</td>
        <td className="px-3 py-2 text-right tabular-nums">{item.setup.toFixed(2)}</td>
        <td className="px-3 py-2 text-right tabular-nums text-mute">{item.risk.toFixed(2)}</td>
        <td className={cn("px-3 py-2 text-right tabular-nums", signedClass(item.ebitda_growth_1y))}>
          {formatSignedPct(item.ebitda_growth_1y)}
        </td>
      </tr>
      {item.memo ? (
        <tr className="border-b border-line bg-panel/40">
          <td colSpan={9} className="px-3 py-3 text-[13px] leading-6 text-mute">
            <p>
              <span className="text-white">Why. </span>
              {item.memo.why_scored}
            </p>
            <p className="mt-2">
              <span className="text-white">10-Q. </span>
              {item.memo.what_10q_changed}
            </p>
            <p className="mt-2">
              <span className="text-white">Invalidation. </span>
              {item.memo.invalidation}
            </p>
            <p className="mt-2">
              <span className="text-white">Caveats. </span>
              {item.memo.caveats}
            </p>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function signedClass(value: number | null): string {
  if (value == null || value === 0) {
    return "text-mute";
  }
  return value > 0 ? "text-up" : "text-down";
}

function formatSignedPct(value: number | null): string {
  if (value == null) {
    return "—";
  }
  const pct = value * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}
