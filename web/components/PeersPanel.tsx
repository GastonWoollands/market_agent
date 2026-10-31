import { PeerScatter } from "@/components/PeerScatter";
import { TickerLink } from "@/components/TickerLink";
import { Panel } from "@/components/Panel";
import { cn } from "@/lib/cn";
import type { PeerRow, TickerPeers } from "@/lib/api";
import { DASH, fmtMultiple, fmtNumber, fmtPct, fmtSignedPct, fmtUsd, signedClass } from "@/lib/format";

export function PeersPanel({ peers }: { peers: TickerPeers | null }) {
  if (!peers) {
    return (
      <Panel title="Peers">
        <p className="text-[13px] text-mute">
          No sector peers: the name has no stored sector or its sector has no valuation members.
        </p>
      </Panel>
    );
  }
  const others = peers.rows.filter((row) => !row.is_self);
  return (
    <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
      <Panel
        title={`Peers · ${peers.sector}`}
        note={`${others.length} nearest by market cap · medians over ${peers.sector_size} names`}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-line text-[11px] uppercase tracking-wide text-mute">
                <th className="px-2 py-1.5 font-normal">Ticker</th>
                <th className="px-2 py-1.5 text-right font-normal">Mkt cap</th>
                <th className="px-2 py-1.5 text-right font-normal">EV/EBITDA</th>
                <th className="px-2 py-1.5 text-right font-normal">5y %ile</th>
                <th className="px-2 py-1.5 text-right font-normal">FCF yld</th>
                <th className="px-2 py-1.5 text-right font-normal">ND/EBITDA</th>
                <th className="px-2 py-1.5 text-right font-normal">EBITDA 1y</th>
                <th className="px-2 py-1.5 text-right font-normal">Ret 1y</th>
                <th className="px-2 py-1.5 text-right font-normal">Vol 1y</th>
                <th className="px-2 py-1.5 text-right font-normal">Rank</th>
              </tr>
            </thead>
            <tbody>
              {peers.rows.map((row) => (
                <Row key={row.ticker} row={row} />
              ))}
              <Row row={peers.medians} median />
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel title="EV/EBITDA vs EBITDA growth" note="sector, latest TTM">
        <PeerScatter
          points={peers.scatter}
          peers={others.map((row) => row.ticker)}
          medianMultiple={peers.medians.ev_ebitda}
          medianGrowth={peers.medians.ebitda_growth_1y}
        />
      </Panel>
    </div>
  );
}

function Row({ row, median = false }: { row: PeerRow; median?: boolean }) {
  return (
    <tr
      className={cn(
        "border-b border-line last:border-0",
        row.is_self && "bg-panel-elevated",
        median && "text-text-secondary",
      )}
    >
      <td className="px-2 py-1.5">
        {median ? (
          <span className="text-[11px] uppercase tracking-wide text-mute">Sector median</span>
        ) : (
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: row.is_self ? "#3b82f6" : "#c4800f" }}
            />
            {row.is_self ? <span className="font-medium">{row.ticker}</span> : <TickerLink ticker={row.ticker} />}
          </span>
        )}
      </td>
      <Num value={fmtUsd(row.market_cap)} />
      <Num value={fmtMultiple(row.ev_ebitda)} />
      <Num value={fmtNumber(row.pctile_5y, 0)} />
      <Num value={fmtPct(row.fcf_yield)} />
      <Num value={fmtMultiple(row.nd_ebitda)} />
      <Num value={fmtSignedPct(row.ebitda_growth_1y)} tone={signedClass(row.ebitda_growth_1y)} />
      <Num value={fmtSignedPct(row.ret_1y)} tone={signedClass(row.ret_1y)} />
      <Num value={fmtPct(row.vol_1y, 0)} />
      <Num value={row.rank == null ? DASH : String(row.rank)} />
    </tr>
  );
}

function Num({ value, tone }: { value: string; tone?: string }) {
  return <td className={cn("px-2 py-1.5 text-right tabular-nums", tone)}>{value}</td>;
}
