export const DASH = "—";

export function usd(v: number | null | undefined, digits = 5): string {
  if (v === null || v === undefined) return DASH;
  if (v === 0) return "$0";
  if (Math.abs(v) < 0.00001) return `$${v.toExponential(2)}`;
  return `$${v.toFixed(digits)}`;
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return DASH;
  return `${(v * 100).toFixed(digits)}%`;
}

export function signedPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return DASH;
  const s = (v * 100).toFixed(digits);
  return `${v > 0 ? "+" : ""}${s}%`;
}

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return DASH;
  if (v >= 10_000) return `${(v / 1000).toFixed(1)} s`;
  return `${Math.round(v).toLocaleString()} ms`;
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return DASH;
  return v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function ci(v: [number, number] | null | undefined, asPct = true): string {
  if (!v) return DASH;
  return asPct ? `[${pct(v[0], 0)}, ${pct(v[1], 0)}]` : `[${v[0].toFixed(3)}, ${v[1].toFixed(3)}]`;
}

export function signedCi(v: [number, number] | null | undefined): string {
  if (!v) return DASH;
  return `[${signedPct(v[0])}, ${signedPct(v[1])}]`;
}

export function when(ts: number | null | undefined): string {
  if (!ts) return DASH;
  return new Date(ts * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function sci(v: number | null | undefined, unit: string): string {
  if (v === null || v === undefined) return DASH;
  if (v === 0) return `0 ${unit}`;
  if (Math.abs(v) < 0.01) return `${v.toExponential(2)} ${unit}`;
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 3 })} ${unit}`;
}
