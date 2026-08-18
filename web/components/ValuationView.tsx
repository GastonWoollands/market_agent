import { cn } from "@/lib/cn";
import type { ValuationMember, ValuationTape } from "@/lib/api";

const SORTS = [
  { id: "pctile", label: "5y %ile" },
  { id: "ev_ebitda", label: "EV/EBITDA" },
  { id: "growth", label: "EBITDA growth" },
  { id: "rerate", label: "Re-rate" },
  { id: "revenue", label: "Revenue" },
  { id: "ticker", label: "Ticker" },
] as const;

export function ValuationView({
  tape,
  query,
}: {
  tape: ValuationTape | null;
  query: { q: string; industry: string; sort: string; min_rev: string };
}) {
  if (tape == null) {
    return <p className="text-sm text-mute">Valuation API unreachable. Start uvicorn, then refresh.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Valuation</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            EV/EBITDA from stored prices and SEC TTM. Percentile is vs that name’s own 5y daily
            multiple. 1y change splits into EBITDA growth × multiple re-rating.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.comparable_n} of {tape.comparable_m} with a comparable multiple
          {tape.as_of ? (
            <>
              <span className="mx-2 text-line">·</span>
              as of {tape.as_of}
            </>
          ) : null}
          {tape.stale ? (
            <>
              <span className="mx-2 text-line">·</span>
              stale
            </>
          ) : null}
        </p>
      </div>

      <form method="get" action="/valuation" className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] uppercase tracking-wide text-mute">
          Search
          <input
            name="q"
            defaultValue={query.q}
            placeholder="Ticker or name"
            className="mt-1 block h-8 w-44 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
          />
        </label>
        <label className="text-[11px] uppercase tracking-wide text-mute">
          Min rev
          <input
            name="min_rev"
            defaultValue={query.min_rev}
            placeholder="e.g. 5000000000"
            className="mt-1 block h-8 w-40 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
          />
        </label>
        <label className="text-[11px] uppercase tracking-wide text-mute">
          Industry
          <select
            name="industry"
            defaultValue={query.industry}
            className="mt-1 block h-8 w-40 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
          >
            <option value="">All</option>
            {tape.industries.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
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

      {tape.members.length === 0 && tape.comparable_n === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.ingest_sec</code>,{" "}
          <code className="text-white">python -m jobs.ingest_yahoo --universe valuation</code>, then{" "}
          <code className="text-white">python -m jobs.compute_valuation</code>.
        </p>
      ) : tape.members.length === 0 ? (
        <p className="text-sm text-mute">No names match these filters.</p>
      ) : (
        <section className="overflow-hidden rounded border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wide text-mute">
              <tr className="border-b border-line">
                <th className="px-3 py-2 font-normal">Ticker</th>
                <th className="px-3 py-2 font-normal">Name</th>
                <th className="px-3 py-2 text-right font-normal">EV/EBITDA</th>
                <th className="px-3 py-2 text-right font-normal">5y %ile</th>
                <th className="px-3 py-2 text-right font-normal">EBITDA 1y</th>
                <th className="px-3 py-2 text-right font-normal">Re-rate 1y</th>
                <th className="px-3 py-2 text-right font-normal">Rev</th>
              </tr>
            </thead>
            <tbody>
              {tape.members.map((row) => (
                <MemberRow key={row.ticker} item={row} />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function MemberRow({ item }: { item: ValuationMember }) {
  return (
    <tr className="border-b border-line last:border-0">
      <td className="px-3 py-2 font-medium">{item.ticker}</td>
      <td className="px-3 py-2 text-mute">{item.name}</td>
      <td className="px-3 py-2 text-right tabular-nums">
        {item.comparable ? formatMultiple(item.ev_ebitda) : "—"}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{formatPctile(item.pctile_5y)}</td>
      <td className={cn("px-3 py-2 text-right tabular-nums", signedClass(item.ebitda_growth_1y))}>
        {formatSignedPct(item.ebitda_growth_1y)}
      </td>
      <td className={cn("px-3 py-2 text-right tabular-nums", signedClass(item.multiple_change_1y))}>
        {formatSignedPct(item.multiple_change_1y)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-mute">{formatUsd(item.revenue)}</td>
    </tr>
  );
}

function signedClass(value: number | null): string {
  if (value == null || value === 0) {
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

function formatSignedPct(value: number | null): string {
  if (value == null) {
    return "—";
  }
  const pct = value * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function formatUsd(value: number | null): string {
  if (value == null) {
    return "—";
  }
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000_000) {
    return `${(value / 1_000_000_000_000).toFixed(2)}T`;
  }
  if (abs >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(1)}B`;
  }
  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(0)}M`;
  }
  return value.toFixed(0);
}
