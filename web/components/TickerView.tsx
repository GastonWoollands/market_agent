import type { ReactNode } from "react";

import { CreditCurvePanel } from "@/components/CreditCurvePanel";
import { CreditImpliedPanel } from "@/components/CreditImpliedPanel";
import { Panel } from "@/components/Panel";
import { PeersPanel } from "@/components/PeersPanel";
import { StaleBadge } from "@/components/StaleBadge";
import { TradingViewChart } from "@/components/TradingViewChart";
import { cn } from "@/lib/cn";
import type { CreditCurve, TickerDesk, TickerRisk, TickerTape, TickerTechnicals } from "@/lib/api";
import {
  DASH,
  fmtMultiple,
  fmtNumber,
  fmtPct,
  fmtPrice,
  fmtShares,
  fmtSignedPct,
  fmtUsd,
  signedClass,
} from "@/lib/format";

export function TickerView({ tape, credit }: { tape: TickerTape; credit: CreditCurve | null }) {
  const id = tape.identity;
  if (id == null) {
    return <p className="text-sm text-mute">No identity stored for this name.</p>;
  }
  const price = tape.price;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{id.ticker}</h1>
            <span className="text-sm text-mute">{id.name}</span>
          </div>
          <p className="mt-2 text-[13px] text-mute">
            {[id.sector ? `${id.sector} (SIC, approx.)` : null, id.industry, id.exchange]
              .filter(Boolean)
              .join(" · ") || "No sector stored"}
            {id.universes.length ? (
              <>
                <span className="mx-2 text-line">·</span>
                {id.universes.join(", ")}
              </>
            ) : (
              <>
                <span className="mx-2 text-line">·</span>
                outside every universe
              </>
            )}
          </p>
        </div>
        <div className="text-right">
          {price ? (
            <p className="text-2xl font-semibold tabular-nums">
              {fmtPrice(price.close)}{" "}
              <span className={cn("text-base", signedClass(price.change_1d))}>
                {fmtSignedPct(price.change_1d, 2)}
              </span>
            </p>
          ) : null}
          <p className="mt-1 text-[13px] text-mute">
            {price ? `close ${price.as_of} · delayed` : "no stored bars"}
            {tape.stale ? (
              <>
                <span className="mx-2 text-line">·</span>
                <StaleBadge stale />
              </>
            ) : null}
          </p>
        </div>
      </div>

      {tape.hint ? <p className="text-sm text-mute">{tape.hint}</p> : null}

      <form method="get" action="/compare" className="flex flex-wrap items-end gap-2">
        <input type="hidden" name="tickers" value={id.ticker} />
        <label className="text-[11px] uppercase tracking-wide text-mute">
          Compare with
          <input
            name="with"
            placeholder="e.g. MSFT,NVDA"
            className="mt-1 block h-8 w-48 rounded border border-line bg-panel px-2 text-[13px] text-white outline-none"
          />
        </label>
        <button
          type="submit"
          className="h-8 rounded border border-line bg-panel px-3 text-[13px] text-white"
        >
          Compare
        </button>
      </form>

      <div className="grid gap-4 lg:grid-cols-2">
        <DeskPanel desk={tape.desk} />
        <SolvencyPanel desk={tape.desk} />
        <TechnicalsPanel tech={tape.technicals} sectorEtf={id.sector_etf} />
        <RiskPanel risk={tape.risk} />
      </div>

      <PeersPanel peers={tape.peers} />
      <CreditImpliedPanel credit={tape.credit} />
      <CreditCurvePanel curve={credit} highlight={tape.credit?.bucket ?? null} />

      {price ? (
        <section className="h-[420px] overflow-hidden rounded border border-line">
          <TradingViewChart symbol={id.tv_symbol} />
        </section>
      ) : null}

      <TtmTable tape={tape} />
      <FyTable tape={tape} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Next events">
          {tape.events.length === 0 ? (
            <p className="text-[13px] text-mute">
              No stored events. Earnings dates are fetched for Watchlist names.
            </p>
          ) : (
            <ul className="space-y-1 text-[13px]">
              {tape.events.map((item) => (
                <li key={`${item.date}-${item.title}`}>
                  <span className="tabular-nums text-mute">{item.date}</span> {item.title}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="News">
          {tape.news.length === 0 ? (
            <p className="text-[13px] text-mute">No stored headlines for this name.</p>
          ) : (
            <ul className="space-y-1.5 text-[13px]">
              {tape.news.map((item) => (
                <li key={item.url}>
                  <span className="tabular-nums text-mute">{item.published_at.slice(0, 10)}</span>{" "}
                  <a href={item.url} target="_blank" rel="noreferrer" className="hover:underline">
                    {item.title}
                  </a>{" "}
                  <span className="text-mute">· {item.publisher}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <p className="text-[12px] text-mute">Delayed research snapshot from stored data. Not advice.</p>
    </div>
  );
}

function DeskPanel({ desk }: { desk: TickerDesk | null }) {
  if (desk == null) {
    return (
      <Panel title="Valuation">
        <p className="text-[13px] text-mute">No SEC TTM stored for this name.</p>
      </Panel>
    );
  }
  const pctNote = desk.comparable
    ? `${desk.sample_size ?? DASH} sessions`
    : desk.sample_size != null
      ? `${desk.sample_size} sessions, needs ~3y`
      : "not in valuation universe";
  return (
    <Panel
      title="Valuation"
      note={`TTM ${desk.ttm_as_of ?? DASH}${desk.ev_basis === "read_time" ? " · EV read-time" : ""}`}
    >
      <Stats>
        <Stat label="EV/EBITDA" value={fmtMultiple(desk.ev_ebitda)} />
        <Stat label="5y %ile" value={fmtNumber(desk.pctile_5y, 0)} note={pctNote} />
        <Stat label="FCF yield" value={fmtPct(desk.fcf_yield)} />
        <Stat label="ND/EBITDA" value={fmtMultiple(desk.nd_ebitda)} />
        <Stat
          label="EBITDA 1y"
          value={fmtSignedPct(desk.ebitda_growth_1y)}
          tone={signedClass(desk.ebitda_growth_1y)}
        />
        <Stat
          label="Revenue 1y"
          value={fmtSignedPct(desk.revenue_growth_1y)}
          tone={signedClass(desk.revenue_growth_1y)}
        />
        <Stat
          label="Rank"
          value={desk.rank != null ? `${desk.rank} / ${desk.ranked ?? DASH}` : DASH}
          note={desk.trap ? "value trap" : undefined}
        />
        <Stat
          label="Accrual"
          value={desk.accrual == null ? DASH : desk.accrual ? "CFO > NI" : "CFO ≤ NI"}
        />
      </Stats>
    </Panel>
  );
}

function SolvencyPanel({ desk }: { desk: TickerDesk | null }) {
  return (
    <Panel title="Solvency & dilution" note="TTM, SEC">
      <Stats>
        <Stat label="Interest cover" value={fmtMultiple(desk?.interest_coverage)} note="EBIT / interest" />
        <Stat
          label="Financing gap"
          value={fmtPct(desk?.financing_gap)}
          note="(capex − CFO) / mkt cap"
        />
        <Stat
          label="Shares 1y"
          value={fmtSignedPct(desk?.share_change_1y)}
          note="+ is dilution"
        />
        <Stat label="Market cap" value={fmtUsd(desk?.market_cap)} />
        <Stat label="EV" value={fmtUsd(desk?.ev)} />
      </Stats>
    </Panel>
  );
}

function TechnicalsPanel({
  tech,
  sectorEtf,
}: {
  tech: TickerTechnicals | null;
  sectorEtf: string | null;
}) {
  if (tech == null) {
    return (
      <Panel title="Technicals">
        <p className="text-[13px] text-mute">No stored bars.</p>
      </Panel>
    );
  }
  return (
    <Panel title="Technicals" note={`close ${tech.as_of}`}>
      <Stats>
        <Stat label="vs SMA 20" value={fmtSignedPct(tech.vs_sma_20)} tone={signedClass(tech.vs_sma_20)} />
        <Stat label="vs SMA 50" value={fmtSignedPct(tech.vs_sma_50)} tone={signedClass(tech.vs_sma_50)} />
        <Stat
          label="vs SMA 200"
          value={fmtSignedPct(tech.vs_sma_200)}
          tone={signedClass(tech.vs_sma_200)}
          note={tech.sma_200 != null ? `SMA ${fmtPrice(tech.sma_200)}` : undefined}
        />
        <Stat label="RSI 14" value={fmtNumber(tech.rsi_14, 0)} />
        <Stat
          label="vs 52w high"
          value={fmtSignedPct(tech.vs_high_52w)}
          tone={signedClass(tech.vs_high_52w)}
          note={`${fmtPrice(tech.low_52w)} – ${fmtPrice(tech.high_52w)}`}
        />
        <Stat label="1m" value={fmtSignedPct(tech.ret_1m)} tone={signedClass(tech.ret_1m)} />
        <Stat label="3m" value={fmtSignedPct(tech.ret_3m)} tone={signedClass(tech.ret_3m)} />
        <Stat label="1y" value={fmtSignedPct(tech.ret_1y)} tone={signedClass(tech.ret_1y)} />
        <Stat
          label="vs SPY 3m / 1y"
          value={`${fmtSignedPct(tech.rel_spy_3m)} / ${fmtSignedPct(tech.rel_spy_1y)}`}
        />
        <Stat
          label={`vs ${sectorEtf ?? "sector"} 3m / 1y`}
          value={`${fmtSignedPct(tech.rel_sector_3m)} / ${fmtSignedPct(tech.rel_sector_1y)}`}
        />
      </Stats>
    </Panel>
  );
}

function RiskPanel({ risk }: { risk: TickerRisk | null }) {
  if (risk == null) {
    return (
      <Panel title="Risk">
        <p className="text-[13px] text-mute">Not enough stored bars.</p>
      </Panel>
    );
  }
  return (
    <Panel
      title="Risk"
      note={`${risk.sessions} sessions · ${risk.source === "risk_stats" ? "stored" : "read-time"}`}
    >
      <Stats>
        <Stat label="Vol 3m" value={fmtPct(risk.vol_3m, 0)} />
        <Stat label="Vol 1y" value={fmtPct(risk.vol_1y, 0)} />
        <Stat label="Downside vol" value={fmtPct(risk.downside_vol_1y, 0)} />
        <Stat label="Beta SPY" value={fmtNumber(risk.beta_spy)} />
        <Stat label="Beta QQQ" value={fmtNumber(risk.beta_qqq)} />
        <Stat label="Corr SPY" value={fmtNumber(risk.corr_spy)} />
        <Stat label="Max DD 1y" value={fmtPct(risk.max_drawdown_1y, 0)} />
        <Stat label="From 1y high" value={fmtPct(risk.drawdown, 0)} />
      </Stats>
    </Panel>
  );
}

function TtmTable({ tape }: { tape: TickerTape }) {
  if (tape.ttm.length === 0) {
    return null;
  }
  const rows = [...tape.ttm].reverse().slice(0, 12);
  return (
    <Panel title="TTM history" note="trailing four quarters, SEC">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-wide text-mute">
            <tr className="border-b border-line">
              {["Quarter", "Revenue", "EBITDA", "EBIT", "CFO", "Capex", "FCF", "Net debt", "Interest", "Shares"].map(
                (label, index) => (
                  <th key={label} className={cn("px-2 py-1.5 font-normal", index > 0 && "text-right")}>
                    {label}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.as_of} className="border-b border-line last:border-0">
                <td className="px-2 py-1.5 tabular-nums">{row.as_of}</td>
                <Num value={fmtUsd(row.revenue)} />
                <Num value={fmtUsd(row.ebitda)} />
                <Num value={fmtUsd(row.ebit)} />
                <Num value={fmtUsd(row.cfo)} />
                <Num value={fmtUsd(row.capex)} />
                <Num value={fmtUsd(row.fcf)} />
                <Num value={fmtUsd(row.net_debt)} />
                <Num value={fmtUsd(row.interest_expense)} />
                <Num value={fmtShares(row.shares)} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function FyTable({ tape }: { tape: TickerTape }) {
  if (tape.fy.length === 0) {
    return null;
  }
  const rows = [...tape.fy].reverse();
  return (
    <Panel title="Fiscal years" note="10-K">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-wide text-mute">
            <tr className="border-b border-line">
              {["FY", "Revenue", "Gross profit", "EBIT", "Net income", "CFO", "LT debt", "Equity", "Shares"].map(
                (label, index) => (
                  <th key={label} className={cn("px-2 py-1.5 font-normal", index > 0 && "text-right")}>
                    {label}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.as_of} className="border-b border-line last:border-0">
                <td className="px-2 py-1.5 tabular-nums">
                  {row.fiscal_year} <span className="text-mute">({row.as_of})</span>
                </td>
                <Num value={fmtUsd(row.revenue)} />
                <Num value={fmtUsd(row.gross_profit)} />
                <Num value={fmtUsd(row.ebit)} />
                <Num value={fmtUsd(row.net_income)} />
                <Num value={fmtUsd(row.cfo)} />
                <Num value={fmtUsd(row.long_term_debt)} />
                <Num value={fmtUsd(row.equity)} />
                <Num value={fmtShares(row.shares)} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Stats({ children }: { children: ReactNode }) {
  return <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">{children}</dl>;
}

function Stat({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: string;
}) {
  return (
    <div>
      <dt className="text-[11px] text-mute">{label}</dt>
      <dd className={cn("text-[15px] tabular-nums", tone)}>{value}</dd>
      {note ? <dd className="text-[11px] text-mute">{note}</dd> : null}
    </div>
  );
}

function Num({ value }: { value: string }) {
  return <td className="px-2 py-1.5 text-right tabular-nums">{value}</td>;
}
