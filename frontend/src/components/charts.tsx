"use client";

import { useState } from "react";

/** Tiny trend line for KPI cards (decorative context; the number beside it is the data). */
export function Sparkline({ values, color = "var(--accent)", width = 96, height = 28 }: { values: (number | null)[]; color?: string; width?: number; height?: number }) {
  const pts = values.map((v, i) => [i, v] as const).filter(([, v]) => v !== null) as [number, number][];
  if (pts.length < 2) return null;
  const xs = values.length - 1 || 1;
  const vs = pts.map(([, v]) => v);
  const lo = Math.min(...vs);
  const hi = Math.max(...vs);
  const y = (v: number) => (hi === lo ? height / 2 : height - 3 - ((v - lo) / (hi - lo)) * (height - 6));
  const d = pts.map(([i, v], k) => `${k ? "L" : "M"}${((i / xs) * width).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = `${d}L${((pts[pts.length - 1][0] / xs) * width).toFixed(1)},${height}L${((pts[0][0] / xs) * width).toFixed(1)},${height}Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="overflow-visible">
      <path d={area} fill={color} opacity={0.12} />
      <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export type Slice = { key: string; label: string; value: number; color: string; display: string };

/** Part-to-whole donut with a 2px surface gap between segments and a centre total. */
export function Donut({ slices, center, sub, size = 180 }: { slices: Slice[]; center: string; sub: string; size?: number }) {
  const [hover, setHover] = useState<string | null>(null);
  const total = slices.reduce((s, x) => s + x.value, 0);
  const r = size / 2 - 14;
  const c = 2 * Math.PI * r;
  let offset = 0;
  const h = slices.find((s) => s.key === hover);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${sub}: ${slices.map((s) => `${s.label} ${s.display}`).join(", ")}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--panel-2)" strokeWidth={26} />
      {total > 0 &&
        slices.map((s) => {
          const len = (s.value / total) * c;
          const gap = slices.filter((x) => x.value > 0).length > 1 ? 2 : 0;
          const el = (
            <circle
              key={s.key}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={hover === s.key ? 30 : 26}
              strokeDasharray={`${Math.max(0, len - gap)} ${c}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              onMouseEnter={() => setHover(s.key)}
              onMouseLeave={() => setHover(null)}
              style={{ transition: "stroke-width .15s", cursor: "default" }}
            >
              <title>{`${s.label}: ${s.display}`}</title>
            </circle>
          );
          offset += len;
          return el;
        })}
      <text x="50%" y="48%" textAnchor="middle" fontSize="24" fontWeight="600" fill="var(--fg)">
        {h ? h.display : center}
      </text>
      <text x="50%" y="60%" textAnchor="middle" fontSize="12" fill="var(--muted)">
        {h ? h.label : sub}
      </text>
    </svg>
  );
}

/** Single-series line chart over days, with crosshair + tooltip on hover. One axis only. */
export function LineChart({
  points,
  format,
  color = "var(--t-medium)",
  height = 220,
}: {
  points: { label: string; value: number | null }[];
  format: (v: number) => string;
  color?: string;
  height?: number;
}) {
  const [hi, setHi] = useState<number | null>(null);
  const W = 640;
  const pad = { l: 56, r: 12, t: 12, b: 28 };
  const vals = points.map((p) => p.value).filter((v): v is number => v !== null);
  if (vals.length === 0) return <div className="flex h-[220px] items-center justify-center text-sm text-muted">No data yet.</div>;
  const max = Math.max(...vals) * 1.15 || 1;
  const n = points.length;
  const x = (i: number) => pad.l + (n === 1 ? (W - pad.l - pad.r) / 2 : (i / (n - 1)) * (W - pad.l - pad.r));
  const y = (v: number) => pad.t + (1 - v / max) * (height - pad.t - pad.b);
  const ticks = [0, max / 3, (2 * max) / 3, max];
  const defined = points.map((p, i) => [i, p.value] as const).filter(([, v]) => v !== null) as [number, number][];
  const line = defined.map(([i, v], k) => `${k ? "L" : "M"}${x(i)},${y(v)}`).join("");
  const area = defined.length > 1 ? `${line}L${x(defined[defined.length - 1][0])},${y(0)}L${x(defined[0][0])},${y(0)}Z` : "";
  const labelEvery = Math.max(1, Math.ceil(n / 6));
  const hp = hi !== null ? points[hi] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={points.map((p) => `${p.label}: ${p.value === null ? "no data" : format(p.value)}`).join("; ")}
        onMouseLeave={() => setHi(null)}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * W;
          const i = n === 1 ? 0 : Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (n - 1));
          setHi(Math.max(0, Math.min(n - 1, i)));
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">
              {format(t)}
            </text>
          </g>
        ))}
        {points.map((p, i) =>
          i % labelEvery === 0 || i === n - 1 ? (
            <text key={i} x={x(i)} y={height - 8} textAnchor="middle" fontSize="11" fill="var(--muted)">
              {p.label}
            </text>
          ) : null,
        )}
        {area && <path d={area} fill={color} opacity={0.1} />}
        <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        {defined.map(([i, v]) => (
          <circle key={i} cx={x(i)} cy={y(v)} r={hi === i ? 5 : 3.5} fill={color} stroke="var(--panel)" strokeWidth={2} />
        ))}
        {hi !== null && <line x1={x(hi)} x2={x(hi)} y1={pad.t} y2={y(0)} stroke="var(--muted)" strokeDasharray="3 3" />}
      </svg>
      {hp && hi !== null && (
        <div
          className="pointer-events-none absolute top-1 rounded-lg border border-border bg-panel px-2.5 py-1.5 text-xs shadow"
          style={{ left: `min(max(${(x(hi) / W) * 100}% - 60px, 0px), calc(100% - 130px))` }}
        >
          <div className="text-muted">{hp.label}</div>
          <div className="font-medium tabular-nums">{hp.value === null ? "no data" : format(hp.value)}</div>
        </div>
      )}
    </div>
  );
}
