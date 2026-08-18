import { cn } from "@/lib/cn";
import type { ValuationMember, ValuationTape } from "@/lib/api";

export function ValuationView({ tape }: { tape: ValuationTape | null }) {
  if (tape == null) {
    return <p className="text-sm text-mute">Valuation API unreachable. Start uvicorn, then refresh.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Valuation</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            US NYSE/Nasdaq names with TTM revenue ≥ $1B and usable four-quarter SEC XBRL (positive
            EBITDA, FCF, shares, net debt). EV/EBITDA versus own 5y range is Day 14. Multiples are
            not computed yet.
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
              stale
            </>
          ) : null}
        </p>
      </div>

      {tape.members.length === 0 ? (
        <p className="text-sm text-mute">
          Run <code className="text-white">python -m jobs.ingest_sec</code>, then{" "}
          <code className="text-white">python -m jobs.ingest_yahoo --universe valuation</code>.
        </p>
      ) : (
        <section className="overflow-hidden rounded border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wide text-mute">
              <tr className="border-b border-line">
                <th className="px-3 py-2 font-normal">Ticker</th>
                <th className="px-3 py-2 font-normal">Name</th>
                <th className="px-3 py-2 font-normal">Exch</th>
                <th className="px-3 py-2 text-right font-normal">TTM rev</th>
                <th className="px-3 py-2 text-right font-normal">EBITDA</th>
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
      <td className="px-3 py-2 text-mute">{item.exchange ?? "—"}</td>
      <td className="px-3 py-2 text-right tabular-nums">{formatUsd(item.revenue)}</td>
      <td className={cn("px-3 py-2 text-right tabular-nums", "text-mute")}>{formatUsd(item.ebitda)}</td>
    </tr>
  );
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
