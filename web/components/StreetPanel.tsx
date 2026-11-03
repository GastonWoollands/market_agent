import { Panel } from "@/components/Panel";
import type { TickerRevision, TickerShortInterest, TickerStreet } from "@/lib/api";
import { DASH, fmtNumber, fmtPct, fmtSignedPct } from "@/lib/format";

export function StreetPanel({ street }: { street: TickerStreet | null }) {
  if (street == null) {
    return null;
  }
  return (
    <Panel title="Short interest and estimate revisions" note="FINRA · Yahoo street consensus">
      <div className="grid gap-6 lg:grid-cols-2">
        <ShortInterest short={street.short} />
        <Revisions street={street} />
      </div>
    </Panel>
  );
}

function ShortInterest({ short }: { short: TickerShortInterest | null }) {
  if (short == null) {
    return <p className="text-[13px] text-mute">No FINRA short interest stored for this name.</p>;
  }
  return (
    <div>
      <dl className="grid grid-cols-3 gap-x-4 gap-y-3">
        <Item
          label="Short, % of shares out"
          value={fmtPct(short.share_of_outstanding, 2)}
          note={`${(short.short_shares / 1e6).toFixed(1)}M shares`}
        />
        <Item
          label="Days to cover"
          value={short.days_to_cover == null ? DASH : fmtNumber(short.days_to_cover, 1)}
          note="at average daily volume"
        />
        <Item label="Change vs prior" value={fmtSignedPct(short.change, 1)} note="two weeks earlier" />
      </dl>
      <p className="mt-3 text-[11px] leading-5 text-mute">
        Settlement {short.settlement_date}; FINRA publishes about eight business days later.
        Share of shares outstanding (SEC), not float.
      </p>
    </div>
  );
}

function Revisions({ street }: { street: TickerStreet }) {
  if (street.revisions.length === 0) {
    return <p className="text-[13px] text-mute">{street.revisions_unavailable ?? "No estimates."}</p>;
  }
  return (
    <div>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-left text-[11px] text-mute">
            <th className="pb-2 font-normal">Consensus EPS</th>
            <th className="pb-2 text-right font-normal">EPS</th>
            <th className="pb-2 text-right font-normal">30d</th>
            <th className="pb-2 text-right font-normal">90d</th>
            <th className="pb-2 text-right font-normal">Revisions 30d</th>
          </tr>
        </thead>
        <tbody>
          {street.revisions.map((row) => (
            <RevisionRow key={row.period} row={row} />
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-[11px] leading-5 text-mute">
        Street consensus (vendor data) as of {street.revisions_as_of}: change in the mean EPS
        estimate and the number of analysts raising ↑ or cutting ↓ it. Not our forecast.
      </p>
    </div>
  );
}

function RevisionRow({ row }: { row: TickerRevision }) {
  return (
    <tr className="border-t border-line">
      <td className="py-1.5">{row.label}</td>
      <td className="py-1.5 text-right tabular-nums">{row.eps == null ? DASH : row.eps.toFixed(2)}</td>
      <td className="py-1.5 text-right tabular-nums">{fmtSignedPct(row.change_30d, 1)}</td>
      <td className="py-1.5 text-right tabular-nums">{fmtSignedPct(row.change_90d, 1)}</td>
      <td className="py-1.5 text-right tabular-nums text-text-secondary">
        {row.up_30d == null && row.down_30d == null ? DASH : `↑${row.up_30d ?? 0} ↓${row.down_30d ?? 0}`}
      </td>
    </tr>
  );
}

function Item({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-[11px] text-mute">{label}</dt>
      <dd className="text-[14px] tabular-nums">{value}</dd>
      {note ? <dd className="text-[10px] text-mute">{note}</dd> : null}
    </div>
  );
}
