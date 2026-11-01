import { Panel } from "@/components/Panel";
import type { CreditAnchorRow, TickerCredit } from "@/lib/api";
import { DASH, fmtNumber, fmtPct, fmtUsd } from "@/lib/format";

const SELF_COLOR = "#3b82f6";

export function CreditImpliedPanel({ credit }: { credit: TickerCredit | null }) {
  if (!credit) {
    return null;
  }
  const note = credit.calibration_version
    ? `Merton DD on rating anchors · calibration ${credit.calibration_version}`
    : "Merton DD on rating anchors";
  if (credit.dd == null || credit.bucket == null) {
    return (
      <Panel title="Equity-implied credit" note={note}>
        <p className="text-[13px] text-mute">{credit.unavailable ?? "Not computed."}</p>
        <Agency credit={credit} />
      </Panel>
    );
  }
  return (
    <Panel title="Equity-implied credit" note={note}>
      <div className="grid gap-5 lg:grid-cols-[2fr_3fr]">
        <div className="space-y-3">
          <div>
            <div className="text-[11px] text-mute">Implied bucket</div>
            <div className="text-2xl font-semibold tracking-tight">{label(credit)}</div>
          </div>
          <Agency credit={credit} />
          <p className="text-[13px] text-text-secondary">
            {credit.bucket} index OAS{" "}
            <span className="tabular-nums text-text-primary">
              {credit.bucket_oas_bp == null ? DASH : `${Math.round(credit.bucket_oas_bp)} bp`}
            </span>
            {credit.position === "below" ? ", and this name sits below it" : null}. That is the
            bucket&apos;s market quote, not this name&apos;s spread.
          </p>
        </div>
        <div>
          <Ladder anchors={credit.anchors} dd={credit.dd} />
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <Item label="Distance to default" value={fmtNumber(credit.dd)} />
            <Item label="Market cap (E)" value={fmtUsd(credit.market_cap)} />
            <Item
              label="Default point (F)"
              value={fmtUsd(credit.default_point)}
              note={credit.statement_as_of ? `balance sheet ${credit.statement_as_of}` : undefined}
            />
            <Item label="Equity vol 1y" value={fmtPct(credit.vol_equity, 0)} />
            <Item label="Asset value (V)" value={fmtUsd(credit.asset_value)} />
            <Item label="Asset vol" value={fmtPct(credit.vol_asset, 0)} />
            <Item label="1y Treasury" value={fmtPct(credit.risk_free, 2)} />
            <Item
              label="Basis"
              value={credit.source === "stored" ? "daily job" : "read time"}
              note={credit.as_of ? `close ${credit.as_of}` : undefined}
            />
          </dl>
        </div>
      </div>
      <p className="mt-4 text-[11px] leading-5 text-mute">
        F = current liabilities − current deferred revenue + ½ non-current liabilities. DD is placed
        on the median DD of agency-rated names per bucket. Reads safe for low-vol issuers levered
        by buybacks (KO, MCD, MO) and harsh for high-vol growth names. Not a rank input.
      </p>
    </Panel>
  );
}

function label(credit: TickerCredit): string {
  if (credit.position === "below") {
    return `Below ${credit.bucket}`;
  }
  if (credit.position === "above") {
    return `${credit.bucket} or better`;
  }
  return credit.bucket ?? DASH;
}

function Agency({ credit }: { credit: TickerCredit }) {
  const agency = credit.agency;
  if (!agency) {
    return <p className="text-[12px] text-mute">No agency rating in the calibration set.</p>;
  }
  const text = `${agency.agency} ${agency.rating}${agency.as_of ? ` (${agency.as_of})` : ""}`;
  return (
    <p className="text-[13px]">
      <span className="text-mute">Agency: </span>
      {agency.source ? (
        <a href={agency.source} target="_blank" rel="noreferrer" className="hover:underline">
          {text}
        </a>
      ) : (
        text
      )}
    </p>
  );
}

// DD on a square-root axis: the high-yield anchors (1–3) would otherwise crowd together.
function Ladder({ anchors, dd }: { anchors: CreditAnchorRow[]; dd: number }) {
  if (anchors.length === 0) {
    return null;
  }
  const top = Math.max(dd, ...anchors.map((row) => row.median_dd)) * 1.08;
  const x = (value: number) => `${(Math.sqrt(Math.max(value, 0)) / Math.sqrt(top)) * 100}%`;
  return (
    <div aria-label={`Distance to default ${dd.toFixed(2)} against rating anchors`}>
      <div className="relative h-16">
        <div className="absolute left-0 right-0 top-8 h-px bg-line-strong" />
        {anchors.map((row) => (
          <div
            key={row.bucket}
            className="absolute top-3 -translate-x-1/2 text-center"
            style={{ left: x(row.median_dd) }}
            title={`${row.bucket}: median DD ${row.median_dd.toFixed(2)} over ${row.names} names`}
          >
            <div className="text-[11px] text-text-secondary">{row.bucket}</div>
            <div className="mx-auto mt-0.5 h-3 w-px bg-mute" />
          </div>
        ))}
        <div
          className="absolute top-[26px] -translate-x-1/2"
          style={{ left: x(dd) }}
          title={`This name: DD ${dd.toFixed(2)}`}
        >
          <div
            className="h-3 w-3 rounded-full ring-2 ring-ink"
            style={{ background: SELF_COLOR }}
          />
        </div>
      </div>
      <div className="flex justify-between text-[10px] text-mute">
        <span>0 · default</span>
        <span>distance to default (σ), √ scale →</span>
      </div>
    </div>
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
