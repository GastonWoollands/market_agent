// Shared number and ET time formats. "—" means not stored.

export const DASH = "—";

export function fmtUsd(value: number | null | undefined): string {
  if (value == null) {
    return DASH;
  }
  const abs = Math.abs(value);
  if (abs >= 1e12) {
    return `${(value / 1e12).toFixed(2)}T`;
  }
  if (abs >= 1e9) {
    return `${(value / 1e9).toFixed(1)}B`;
  }
  if (abs >= 1e6) {
    return `${(value / 1e6).toFixed(0)}M`;
  }
  return value.toFixed(0);
}

export function fmtPrice(value: number | null | undefined): string {
  return value == null ? DASH : value.toFixed(2);
}

export function fmtMultiple(value: number | null | undefined, digits = 1): string {
  if (value == null) {
    return DASH;
  }
  // Avoid "-0.0x" for a tiny net-cash position.
  const shown = Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value;
  return `${shown.toFixed(digits)}x`;
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  return value == null ? DASH : `${(value * 100).toFixed(digits)}%`;
}

export function fmtSignedPct(value: number | null | undefined, digits = 1): string {
  if (value == null) {
    return DASH;
  }
  const pct = value * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

export function fmtNumber(value: number | null | undefined, digits = 2): string {
  return value == null ? DASH : value.toFixed(digits);
}

export function fmtShares(value: number | null | undefined): string {
  if (value == null) {
    return DASH;
  }
  return value >= 1e9 ? `${(value / 1e9).toFixed(2)}B` : `${(value / 1e6).toFixed(0)}M`;
}

// Green / red only for signed returns and changes.
export function signedClass(value: number | null | undefined): string {
  if (value == null || value === 0) {
    return "text-mute";
  }
  return value > 0 ? "text-up" : "text-down";
}

// Stored timestamps are UTC; the desk reads them in New York time.
export const ET_ZONE = "America/New_York";

export type EtStyle = "short" | "iso";

/** "Nov 3, 1:02 PM ET" (short) or "2026-11-03 13:02 ET" (iso); the input if unparsable. */
export function fmtEt(value: string, style: EtStyle = "short"): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  if (style === "short") {
    const label = parsed.toLocaleString("en-US", {
      timeZone: ET_ZONE,
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
    return `${label} ET`;
  }
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: ET_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(parsed);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")} ET`;
}

/** Calendar date "YYYY-MM-DD" as "Nov 3"; no time zone shift. */
export function fmtDay(value: string): string {
  const parts = value.split("-").map(Number);
  if (parts.length < 3 || parts.some((part) => Number.isNaN(part))) {
    return value;
  }
  const [year, month, day] = parts;
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
