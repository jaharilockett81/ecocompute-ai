"use client";

import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, children, className = "", right }: { title?: ReactNode; children: ReactNode; className?: string; right?: ReactNode }) {
  return (
    <section className={`card min-w-0 p-4 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="card min-w-0 p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const TONES: Record<string, string> = {
  good: "bg-accent-soft text-accent",
  bad: "bg-bad-soft text-bad",
  warn: "bg-warn-soft text-warn",
  info: "bg-info-soft text-info",
  muted: "bg-panel-2 text-muted",
};

export function Badge({ tone = "muted", children }: { tone?: keyof typeof TONES | string; children: ReactNode }) {
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone] || TONES.muted}`}>{children}</span>;
}

export function statusTone(status?: string | null): string {
  switch (status) {
    case "passed":
    case "completed":
    case "done":
    case "ok":
      return "good";
    case "failed":
    case "error":
    case "interrupted":
      return "bad";
    case "running":
    case "queued":
      return "info";
    case "cancelled":
    case "budget_stopped":
    case "unverified":
      return "warn";
    default:
      return "muted";
  }
}

export function tierColor(tier?: string | null): string {
  return tier === "small" ? "var(--t-small)" : tier === "medium" ? "var(--t-medium)" : tier === "large" ? "var(--t-large)" : "var(--muted)";
}

export function TierBadge({ tier, label }: { tier?: string | null; label?: string }) {
  if (!tier) return <span className="text-muted">—</span>;
  const c = tierColor(tier);
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium" style={{ color: c }}>
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: c }} />
      {label || tier}
    </span>
  );
}

export function ErrorBox({ error, hint }: { error: string | null | undefined; hint?: ReactNode }) {
  if (!error) return null;
  return (
    <div className="mb-4 rounded-lg border border-bad/40 bg-bad-soft p-3 text-sm text-bad">
      <div className="font-medium">{error}</div>
      {hint && <div className="mt-1 text-fg/80">{hint}</div>}
    </div>
  );
}

export function SampleBanner({ show }: { show?: boolean }) {
  if (!show) return null;
  return (
    <div className="mb-4 rounded-lg border border-warn/40 bg-warn-soft p-3 text-sm text-warn">
      <strong>Sample data.</strong> The backend is running the offline mock provider, so these numbers are placeholders, not
      measurements from Nebius. Configure <code>NEBIUS_API_KEY</code> on the backend to see real results.
    </div>
  );
}

/** Horizontal bars for a {label: value} map. */
export function Bars({
  data,
  format = (v) => String(v),
  color,
  max,
}: {
  data: { key: string; label?: ReactNode; value: number | null | undefined; color?: string; note?: ReactNode }[];
  format?: (v: number) => ReactNode;
  color?: string;
  max?: number;
}) {
  const m = max ?? Math.max(1e-12, ...data.map((d) => d.value ?? 0));
  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d.key} className="text-sm">
          <div className="mb-0.5 flex justify-between gap-2">
            <span className="truncate">{d.label ?? d.key}</span>
            <span className="tabular-nums text-muted">
              {d.value === null || d.value === undefined ? "—" : format(d.value)}
              {d.note && <span className="ml-2">{d.note}</span>}
            </span>
          </div>
          <div className="h-2 rounded-full bg-panel-2">
            <div
              className="h-2 rounded-full"
              style={{ width: `${Math.max(0, Math.min(100, ((d.value ?? 0) / m) * 100))}%`, background: d.color || color || "var(--accent)" }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function KV({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-sm">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Loading() {
  return <div className="text-sm text-muted">Loading…</div>;
}

export function BackendHint() {
  return (
    <span>
      Is the backend running? Check the API URL in <a className="underline" href="/settings">Settings</a>.
    </span>
  );
}
