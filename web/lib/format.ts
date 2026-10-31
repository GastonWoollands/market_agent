// Shared number formats for the Ticker and Compare pages. "—" means not stored.

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
