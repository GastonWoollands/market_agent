import type { Positioning, PositioningTrader } from "@/lib/api";
import { DASH, fmtSignedPct } from "@/lib/format";

export function PositioningPanel({ positioning }: { positioning: Positioning | null }) {
  if (positioning == null) {
    return <p className="text-[13px] text-mute">Positioning API unreachable.</p>;
  }
  if (positioning.as_of == null) {
    return (
      <p className="text-[13px] text-mute">
        No CFTC reports stored. Run <code className="text-white">make cftc-backfill</code>.
      </p>
    );
  }
  return (
    <div className="max-w-3xl space-y-2">
      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full min-w-[520px] text-[13px]">
          <thead>
            <tr className="border-b border-line text-left text-[11px] text-mute">
              <th className="px-3 py-2 font-normal">Futures</th>
              <th className="px-3 py-2 text-right font-normal">Asset managers, net</th>
              <th className="px-3 py-2 text-right font-normal">3y percentile</th>
              <th className="px-3 py-2 text-right font-normal">Leveraged funds, net</th>
              <th className="px-3 py-2 text-right font-normal">3y percentile</th>
            </tr>
          </thead>
          <tbody>
            {positioning.rows.map((row) => (
              <tr key={row.key} className="border-b border-line last:border-0">
                <td className="px-3 py-2">{row.label}</td>
                <Net trader={row.asset_managers} />
                <Percentile trader={row.asset_managers} />
                <Net trader={row.leveraged_funds} />
                <Percentile trader={row.leveraged_funds} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] leading-5 text-mute">
        Net = long − short contracts as a share of open interest; positive is net long. Asset
        managers are pensions, insurers and long-only funds; leveraged funds are hedge funds and
        CTAs. Report of {positioning.as_of}. Context, not a timing signal.
      </p>
    </div>
  );
}

function Net({ trader }: { trader: PositioningTrader | null }) {
  return (
    <td className="px-3 py-2 text-right tabular-nums">
      {trader == null ? DASH : fmtSignedPct(trader.share_oi, 1)}
    </td>
  );
}

function Percentile({ trader }: { trader: PositioningTrader | null }) {
  const pct = trader?.pct_3y;
  return (
    <td className="px-3 py-2 text-right tabular-nums text-text-secondary">
      {pct == null ? DASH : `${Math.round(pct * 100)}`}
    </td>
  );
}
