import { RrgScatter } from "@/components/RrgScatter";
import { cn } from "@/lib/cn";
import type { DynamicsMember, DynamicsTape } from "@/lib/api";

const QUADRANTS = [
  { id: "leading", label: "Leading" },
  { id: "weakening", label: "Weakening" },
  { id: "lagging", label: "Lagging" },
  { id: "improving", label: "Improving" },
] as const;

const QUADRANT_DOT: Record<string, string> = {
  leading: "bg-up",
  weakening: "bg-[#d4a017]",
  lagging: "bg-down",
  improving: "bg-[#6cb6ff]",
};

export function DynamicsView({ tape }: { tape: DynamicsTape | null }) {
  if (tape == null) {
    return <p className="text-sm text-mute">Dynamics API unreachable. Start uvicorn, then refresh.</p>;
  }

  const grouped = Object.fromEntries(
    QUADRANTS.map((quadrant) => [
      quadrant.id,
      tape.members.filter((item) => item.quadrant === quadrant.id),
    ]),
  ) as Record<(typeof QUADRANTS)[number]["id"], DynamicsMember[]>;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dynamics</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mute">
            JdK RS-Ratio / RS-Momentum vs {tape.benchmark} from stored daily bars. Origin is 100 / 100.
            Trails are weekly. Relative overlay is Day 8.
          </p>
        </div>
        <p className="text-[13px] text-mute">
          {tape.as_of ? <>as of {tape.as_of}</> : "no RRG rows"}
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
          Run <code className="text-white">python -m jobs.compute_dynamics</code> after{" "}
          <code className="text-white">ingest_yahoo</code>, then refresh.
        </p>
      ) : null}

      <section className="overflow-hidden rounded border border-line bg-panel">
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <h2 className="text-[11px] uppercase tracking-wide text-mute">RRG</h2>
          <p className="text-[11px] text-mute">
            <span className="text-up">Leading</span>
            <span className="mx-1.5 text-line">·</span>
            <span className="text-[#d4a017]">Weakening</span>
            <span className="mx-1.5 text-line">·</span>
            <span className="text-down">Lagging</span>
            <span className="mx-1.5 text-line">·</span>
            <span className="text-[#6cb6ff]">Improving</span>
          </p>
        </div>
        <RrgScatter members={tape.members} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {QUADRANTS.map((quadrant) => (
          <QuadrantList
            key={quadrant.id}
            title={quadrant.label}
            accent={QUADRANT_DOT[quadrant.id]}
            items={grouped[quadrant.id]}
          />
        ))}
      </section>
    </div>
  );
}

function QuadrantList({
  title,
  accent,
  items,
}: {
  title: string;
  accent: string;
  items: DynamicsMember[];
}) {
  return (
    <div className="overflow-hidden rounded border border-line">
      <h2 className="flex items-center gap-2 border-b border-line px-3 py-2 text-[11px] uppercase tracking-wide text-mute">
        <span className={cn("h-1.5 w-1.5 rounded-full", accent)} />
        {title}
        <span className="ml-auto tabular-nums">{items.length}</span>
      </h2>
      {items.length === 0 ? (
        <p className="px-3 py-3 text-[13px] text-mute">None</p>
      ) : (
        items.map((item, index) => (
          <div
            key={item.ticker}
            className={cn(
              "flex items-center gap-3 px-3 py-2",
              index < items.length - 1 ? "border-b border-line" : "",
            )}
          >
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium">{item.ticker}</p>
              <p className="truncate text-[11px] text-mute">{item.sector ?? item.name}</p>
            </div>
            <Spark points={item.indexed} />
            <span className={cn("w-14 text-right text-[13px] tabular-nums", changeClass(item.ret_1m))}>
              {formatPct(item.ret_1m)}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

function Spark({ points }: { points: { date: string; value: number }[] }) {
  if (points.length < 2) {
    return <span className="w-[72px] shrink-0" />;
  }
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 72;
  const height = 24;
  const d = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * (height - 2) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <polyline fill="none" stroke={up ? "#3dd68c" : "#ef5b5b"} strokeWidth="1.25" points={d} />
    </svg>
  );
}

function formatPct(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  const abs = Math.abs(value).toFixed(1);
  if (value > 0) {
    return `+${abs}%`;
  }
  if (value < 0) {
    return `-${abs}%`;
  }
  return `${abs}%`;
}

function changeClass(value: number | null): string {
  if (value == null || value === 0) {
    return "text-mute";
  }
  return value > 0 ? "text-up" : "text-down";
}
