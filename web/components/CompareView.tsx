import { CorrHeatmap } from "@/components/CorrHeatmap";
import { RelativeOverlay } from "@/components/RelativeOverlay";
import { StaleBadge } from "@/components/StaleBadge";
import { TickerLink } from "@/components/TickerLink";
import { Panel } from "@/components/TickerView";
import { cn } from "@/lib/cn";
import type { CompareRow, CompareTape } from "@/lib/api";
import {
  DASH,
  fmtMultiple,
  fmtNumber,
  fmtPct,
  fmtPrice,
  fmtSignedPct,
  fmtUsd,
  signedClass,
} from "@/lib/format";

type Metric = {
  label: string;
  value: (row: CompareRow) => number | null | undefined;
  format: (value: number | null | undefined) => string;
  signed?: boolean;
};

const GROUPS: { title: string; metrics: Metric[] }[] = [
  {
    title: "Price",
    metrics: [
      { label: "Close", value: (r) => r.price?.close, format: fmtPrice },
      { label: "1d", value: (r) => r.price?.change_1d, format: (v) => fmtSignedPct(v, 2), signed: true },
      { label: "3m", value: (r) => r.technicals?.ret_3m, format: fmtSignedPct, signed: true },
      { label: "1y", value: (r) => r.technicals?.ret_1y, format: fmtSignedPct, signed: true },
      { label: "vs SPY 1y", value: (r) => r.technicals?.rel_spy_1y, format: fmtSignedPct, signed: true },
      { label: "vs SMA 200", value: (r) => r.technicals?.vs_sma_200, format: fmtSignedPct, signed: true },
      { label: "vs 52w high", value: (r) => r.technicals?.vs_high_52w, format: fmtSignedPct, signed: true },
      { label: "RSI 14", value: (r) => r.technicals?.rsi_14, format: (v) => fmtNumber(v, 0) },
    ],
  },
  {
    title: "Valuation",
    metrics: [
      { label: "Market cap", value: (r) => r.desk?.market_cap, format: fmtUsd },
      { label: "EV/EBITDA", value: (r) => r.desk?.ev_ebitda, format: fmtMultiple },
      { label: "5y %ile", value: (r) => r.desk?.pctile_5y, format: (v) => fmtNumber(v, 0) },
      { label: "FCF yield", value: (r) => r.desk?.fcf_yield, format: fmtPct },
      { label: "EBITDA 1y", value: (r) => r.desk?.ebitda_growth_1y, format: fmtSignedPct, signed: true },
      { label: "Revenue 1y", value: (r) => r.desk?.revenue_growth_1y, format: fmtSignedPct, signed: true },
      { label: "Rank", value: (r) => r.desk?.rank, format: (v) => (v == null ? DASH : String(v)) },
    ],
  },
  {
    title: "Solvency & dilution",
    metrics: [
      { label: "ND/EBITDA", value: (r) => r.desk?.nd_ebitda, format: fmtMultiple },
      { label: "Interest cover", value: (r) => r.desk?.interest_coverage, format: fmtMultiple },
      { label: "Financing gap", value: (r) => r.desk?.financing_gap, format: fmtPct },
      { label: "Shares 1y", value: (r) => r.desk?.share_change_1y, format: fmtSignedPct },
    ],
  },
  {
    title: "Risk",
    metrics: [
      { label: "Vol 1y", value: (r) => r.risk?.vol_1y, format: (v) => fmtPct(v, 0) },
      { label: "Downside vol", value: (r) => r.risk?.downside_vol_1y, format: (v) => fmtPct(v, 0) },
      { label: "Beta SPY", value: (r) => r.risk?.beta_spy, format: fmtNumber },
      { label: "Beta QQQ", value: (r) => r.risk?.beta_qqq, format: fmtNumber },
      { label: "Max DD 1y", value: (r) => r.risk?.max_drawdown_1y, format: (v) => fmtPct(v, 0) },
      { label: "From 1y high", value: (r) => r.risk?.drawdown, format: (v) => fmtPct(v, 0) },
    ],
  },
];

export function CompareView({ tape, query }: { tape: CompareTape | null; query: string }) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Compare</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            Two to six names side by side on stored data: desk metrics, solvency, risk, 1y
            performance rebased to 100 and the correlation of daily returns. Side by side only —
            not a rotation plan.
          </p>
        </div>
        {tape ? (
          <p className="text-[13px] text-mute">
            {tape.as_of ? `as of ${tape.as_of}` : null}
            {tape.stale ? (
              <>
                <span className="mx-2 text-line">·</span>
                <StaleBadge stale />
              </>
            ) : null}
          </p>
        ) : null}
      </div>

      <form method="get" action="/compare" className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] uppercase tracking-wide text-mute">
          Tickers
          <input
            name="tickers"
            defaultValue={query}
            placeholder="MSFT,META,NVDA"
            className="mt-1 block h-8 w-72 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
          />
        </label>
        <button
          type="submit"
          className="h-8 rounded border border-line bg-panel px-3 text-[13px] text-white"
        >
          Apply
        </button>
      </form>

      {tape == null ? (
        <p className="text-sm text-mute">
          Enter 2 to 6 stored tickers, comma separated. If this persists, the API is unreachable.
        </p>
      ) : (
        <>
          {tape.missing.length ? (
            <p className="text-sm text-mute">
              Not stored: {tape.missing.join(", ")}. Add them to the Watchlist to hydrate.
            </p>
          ) : null}
          <CompareTable rows={tape.rows} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="1y performance" note="rebased to 100, adjusted closes">
              <div className="h-[320px]">
                <RelativeOverlay series={tape.overlay} benchmark={tape.benchmark} />
              </div>
            </Panel>
            <Panel title="Correlation" note={tape.corr ? `${tape.corr.window} daily returns` : undefined}>
              <CorrHeatmap
                corr={tape.corr}
                names={Object.fromEntries(tape.rows.map((row) => [row.identity.ticker, row.identity.name]))}
              />
            </Panel>
          </div>
          <p className="text-[12px] text-mute">Delayed research snapshot from stored data. Not advice.</p>
        </>
      )}
    </div>
  );
}

function CompareTable({ rows }: { rows: CompareRow[] }) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <section className="overflow-x-auto rounded border border-line">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="border-b border-line">
            <th className="px-3 py-2 text-[11px] font-normal uppercase tracking-wide text-mute">Metric</th>
            {rows.map((row) => (
              <th key={row.identity.ticker} className="px-3 py-2 text-right font-medium">
                <TickerLink ticker={row.identity.ticker} />
                <div className="text-[11px] font-normal text-mute">{row.identity.sector ?? DASH}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {GROUPS.map((group) => (
            <Group key={group.title} title={group.title} metrics={group.metrics} rows={rows} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Group({ title, metrics, rows }: { title: string; metrics: Metric[]; rows: CompareRow[] }) {
  return (
    <>
      <tr className="border-b border-line bg-panel">
        <td colSpan={rows.length + 1} className="px-3 py-1.5 text-[11px] uppercase tracking-wide text-mute">
          {title}
        </td>
      </tr>
      {metrics.map((metric) => (
        <tr key={metric.label} className="border-b border-line last:border-0">
          <td className="px-3 py-1.5 text-mute">{metric.label}</td>
          {rows.map((row) => {
            const value = metric.value(row);
            return (
              <td
                key={row.identity.ticker}
                className={cn("px-3 py-1.5 text-right tabular-nums", metric.signed && signedClass(value))}
              >
                {metric.format(value)}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
