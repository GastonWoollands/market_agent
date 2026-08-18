import type { DynamicsCorr, DynamicsMember } from "@/lib/api";

export const QUADRANTS = [
  { id: "leading", label: "Leading", hint: "strong, still gaining" },
  { id: "weakening", label: "Weakening", hint: "strong, but fading" },
  { id: "improving", label: "Improving", hint: "weak, turning up" },
  { id: "lagging", label: "Lagging", hint: "weak, still falling" },
] as const;

export type QuadrantId = (typeof QUADRANTS)[number]["id"];

export const QUADRANT_COLOR: Record<string, string> = {
  leading: "#4ecbcb",
  weakening: "#d4a017",
  lagging: "#ef5b5b",
  improving: "#6cb6ff",
};

export const QUADRANT_TEXT: Record<string, string> = {
  leading: "text-[#4ecbcb]",
  weakening: "text-[#d4a017]",
  lagging: "text-down",
  improving: "text-[#6cb6ff]",
};

export const QUADRANT_DOT: Record<string, string> = {
  leading: "bg-[#4ecbcb]",
  weakening: "bg-[#d4a017]",
  lagging: "bg-down",
  improving: "bg-[#6cb6ff]",
};

export type CorrPair = {
  left: string;
  right: string;
  value: number;
};

export function displayName(member: Pick<DynamicsMember, "name" | "sector" | "ticker">): string {
  return member.name || member.sector || member.ticker;
}

export function quadrantAt(rsRatio: number, rsMomentum: number): string {
  if (rsRatio >= 100 && rsMomentum >= 100) {
    return "leading";
  }
  if (rsRatio >= 100) {
    return "weakening";
  }
  if (rsMomentum >= 100) {
    return "improving";
  }
  return "lagging";
}

export function quadrantLabel(id: string): string {
  return QUADRANTS.find((item) => item.id === id)?.label ?? id;
}

export function priorQuadrant(member: DynamicsMember, daysAgo = 21): string | null {
  if (member.trail.length < 2) {
    return null;
  }
  const latest = member.trail[member.trail.length - 1];
  const target = Date.parse(latest.as_of) - daysAgo * 86_400_000;
  if (Number.isNaN(target)) {
    return null;
  }
  let best = member.trail[0];
  let bestDist = Number.POSITIVE_INFINITY;
  for (const point of member.trail.slice(0, -1)) {
    const stamp = Date.parse(point.as_of);
    if (Number.isNaN(stamp)) {
      continue;
    }
    const dist = Math.abs(stamp - target);
    if (dist < bestDist) {
      best = point;
      bestDist = dist;
    }
  }
  return quadrantAt(best.rs_ratio, best.rs_momentum);
}

export function nameByTicker(members: DynamicsMember[]): Record<string, string> {
  return Object.fromEntries(members.map((item) => [item.ticker, displayName(item)]));
}

export function corrPairs(corr: DynamicsCorr): CorrPair[] {
  const out: CorrPair[] = [];
  const { tickers, matrix } = corr;
  for (let i = 0; i < tickers.length; i += 1) {
    for (let j = 0; j < i; j += 1) {
      const value = matrix[i]?.[j];
      if (value == null || Number.isNaN(value)) {
        continue;
      }
      out.push({ left: tickers[j] ?? "", right: tickers[i] ?? "", value });
    }
  }
  return out;
}

export function averageCorr(pairs: CorrPair[]): number | null {
  if (pairs.length === 0) {
    return null;
  }
  return pairs.reduce((sum, pair) => sum + pair.value, 0) / pairs.length;
}

export function formatSigned(value: number, digits = 1): string {
  const abs = Math.abs(value).toFixed(digits);
  if (value > 0) {
    return `+${abs}`;
  }
  if (value < 0) {
    return `-${abs}`;
  }
  return abs;
}

export function pairHeadline(peakLag: number | null): string {
  if (peakLag == null) {
    return "Not enough overlapping closes for this pair";
  }
  if (peakLag === 0) {
    return "No — they move on the same day";
  }
  return "A lead shows up in this window";
}

export function pairConclusion(
  leftName: string,
  rightName: string,
  peakLag: number | null,
  peakCorr: number | null,
): string {
  if (peakLag == null) {
    return "Not enough overlapping daily closes to compare this pair.";
  }
  const peak =
    peakCorr == null ? "" : ` Peak ${formatSigned(peakCorr, 2)} at ${peakLag === 0 ? "same day" : `lag ${peakLag > 0 ? "+" : ""}${peakLag}`}.`;
  if (peakLag === 0) {
    return `No. They move on the same day.${peak} Knowing one tells you nothing about the other's next session.`;
  }
  const sessions = Math.abs(peakLag);
  const unit = sessions === 1 ? "session" : "sessions";
  const leader = peakLag > 0 ? leftName : rightName;
  const follower = peakLag > 0 ? rightName : leftName;
  return `${leader} tends to move ${sessions} ${unit} before ${follower} in this window.${peak} Not a trading signal.`;
}
