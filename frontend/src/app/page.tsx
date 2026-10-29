"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useApi } from "@/lib/useApi";
import { ms, num, pct, signedPct, usd } from "@/lib/format";
import Icon from "@/components/Icon";
import { Bars, BackendHint, Card, ErrorBox, Loading, PageHeader, SampleBanner, Stat, tierColor } from "@/components/ui";
import { Donut, LineChart, Sparkline, type Slice } from "@/components/charts";

const DAYS = 14;
const DAY = 86400;

function median(xs: number[]) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

type Row = { created_at: number; status: string; latency_ms: number | null; cost_usd: number | null; final_tier: string | null };

function dayStats(rows: Row[]) {
  const graded = rows.filter((r) => r.status === "passed" || r.status === "failed");
  const passed = rows.filter((r) => r.status === "passed");
  const costs = rows.map((r) => r.cost_usd).filter((c): c is number => c !== null);
  return {
    count: rows.length,
    passRate: graded.length ? passed.length / graded.length : null,
    latency: median(rows.map((r) => r.latency_ms).filter((v): v is number => !!v)),
    costPerTask: costs.length ? costs.reduce((a, b) => a + b, 0) / costs.length : null,
    costPerSuccess: costs.length && passed.length ? costs.reduce((a, b) => a + b, 0) / passed.length : null,
  };
}

function ago(ts: number) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function Trend({ v, goodWhenUp }: { v: number | null; goodWhenUp: boolean }) {
  if (v === null || !isFinite(v)) return <span className="text-xs text-muted">no prior week</span>;
  const good = goodWhenUp ? v >= 0 : v <= 0;
  return (
    <span className="inline-flex items-center gap-0.5 text-xs font-medium" style={{ color: good ? "var(--accent)" : "var(--bad)" }}>
      <Icon name={v >= 0 ? "arrowUp" : "arrowDown"} size={13} />
      {signedPct(v, 0)}
      <span className="ml-1 font-normal text-muted">vs prior 7d</span>
    </span>
  );
}

function TierPill({ tier, label }: { tier?: string | null; label?: string }) {
  if (!tier) return <span className="text-muted">—</span>;
  const c = tierColor(tier);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium text-fg" style={{ background: `color-mix(in srgb, ${c} 16%, transparent)` }}>
      <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: c }} />
      {label || tier}
    </span>
  );
}

export default function Overview() {
  const { data: o, error } = useApi<any>("/api/overview");
  const { data: cfg } = useApi<any>("/api/config");
  const { data: models } = useApi<any>("/api/models");
  const { data: wl } = useApi<any>("/api/workloads?limit=200");
  const lb = o?.latest_benchmark;
  const { data: impact } = useApi<any>(lb ? `/api/impact?run_id=${lb.id}` : null);
  const [donutTab, setDonutTab] = useState<"success" | "cost" | "latency">("success");
  const [trendTab, setTrendTab] = useState<"latency" | "cost">("latency");

  const tiers: any[] = useMemo(() => cfg?.tiers || [], [cfg]);
  const label = (k?: string | null) => tiers.find((t) => t.key === k)?.label?.replace("Nemotron ", "") || k || "—";

  const rows: Row[] = useMemo(
    () => (wl?.items || []).filter((w: any) => w.provider === o?.provider && w.status !== "running"),
    [wl, o?.provider],
  );

  const series = useMemo(() => {
    const now = Date.now() / 1000;
    const start = Math.floor(now / DAY) * DAY - (DAYS - 1) * DAY;
    return Array.from({ length: DAYS }, (_, i) => {
      const d0 = start + i * DAY;
      const day = rows.filter((r) => r.created_at >= d0 && r.created_at < d0 + DAY);
      return { label: new Date(d0 * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" }), ...dayStats(day) };
    });
  }, [rows]);

  const weekDelta = (pick: (s: ReturnType<typeof dayStats>) => number | null) => {
    const now = Date.now() / 1000;
    const cur = dayStats(rows.filter((r) => r.created_at >= now - 7 * DAY));
    const prev = dayStats(rows.filter((r) => r.created_at < now - 7 * DAY && r.created_at >= now - 14 * DAY));
    const a = pick(cur);
    const b = pick(prev);
    return a === null || b === null || b === 0 ? null : a / b - 1;
  };

  const byTier = useMemo(() => {
    const out: Record<string, { passed: number; cost: number; lat: number[] }> = {};
    for (const t of tiers) out[t.key] = { passed: 0, cost: 0, lat: [] };
    for (const r of rows) {
      if (!r.final_tier || !out[r.final_tier]) continue;
      if (r.status === "passed") out[r.final_tier].passed += 1;
      if (r.cost_usd !== null) out[r.final_tier].cost += r.cost_usd;
      if (r.latency_ms) out[r.final_tier].lat.push(r.latency_ms);
    }
    return out;
  }, [rows, tiers]);

  const slices: Slice[] = tiers.map((t) => {
    const v = donutTab === "success" ? byTier[t.key]?.passed || 0 : byTier[t.key]?.cost || 0;
    return { key: t.key, label: t.label, value: v, color: tierColor(t.key), display: donutTab === "success" ? num(v) : usd(v, 4) };
  });
  const sliceTotal = slices.reduce((s, x) => s + x.value, 0);

  // Environmental impact: routed condition vs fixed large baseline in the latest benchmark (central scenario).
  const env = useMemo(() => {
    const conds = impact?.conditions;
    const base = conds?.["fixed:large"]?.estimated?.scenarios?.central;
    const routedKey: string | null = conds?.adaptive_warm ? "adaptive_warm" : conds?.adaptive ? "adaptive" : null;
    if (!base || !routedKey) return null;
    const routed = conds[routedKey].estimated.scenarios.central;
    const red = (k: string) => (base[k] ? 1 - routed[k] / base[k] : null);
    const ps = lb?.summary?.conditions;
    return {
      routedKey,
      energy: red("energy_wh"),
      water: red("water_ml"),
      co2: red("co2e_g"),
      passDiff: ps?.[routedKey]?.success_rate != null && ps?.["fixed:large"]?.success_rate != null ? ps[routedKey].success_rate - ps["fixed:large"].success_rate : null,
    };
  }, [impact, lb]);

  const tierStatus = models?.tiers ? `${models.tiers.filter((t: any) => t.in_catalog).length}/${models.tiers.length} models` : "—";

  return (
    <div>
      <PageHeader
        title="EcoCompute"
        subtitle="Inference optimization for a more efficient AI future."
        actions={
          <Link href="/playground" className="btn btn-primary">
            <Icon name="play" size={16} /> Run Workload
          </Link>
        }
      />
      <ErrorBox error={error} hint={<BackendHint />} />
      <SampleBanner show={o?.sample_data} />
      {!o && !error && <Loading />}
      {o && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              icon="doc"
              value={num(o.workloads_total)}
              label="Workloads processed"
              extra={<div className="mt-2 flex items-end justify-between gap-2"><Trend v={weekDelta((s) => s.count)} goodWhenUp /><Sparkline values={series.map((s) => s.count)} /></div>}
            />
            <Stat
              icon="check"
              value={pct(o.quality_pass_rate, 0)}
              label="Quality pass rate"
              extra={<div className="mt-2 flex items-end justify-between gap-2"><Trend v={weekDelta((s) => s.passRate)} goodWhenUp /><Sparkline values={series.map((s) => s.passRate)} /></div>}
            />
            <Stat
              icon="clock"
              iconTone="info"
              value={ms(o.latency_ms_median)}
              label="Median latency"
              extra={<div className="mt-2 flex items-end justify-between gap-2"><Trend v={weekDelta((s) => s.latency)} goodWhenUp={false} /><Sparkline values={series.map((s) => s.latency)} color="var(--t-medium)" /></div>}
            />
            <Stat
              icon="dollar"
              value={usd(o.cost_per_success_usd, 4)}
              label="Cost per successful task"
              extra={<div className="mt-2 flex items-end justify-between gap-2"><Trend v={weekDelta((s) => s.costPerSuccess)} goodWhenUp={false} /><Sparkline values={series.map((s) => s.costPerSuccess)} /></div>}
            />
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Card
              title="Model Selection"
              subtitle={donutTab === "success" ? "Distribution of models used for successful tasks" : donutTab === "cost" ? "Share of inference cost by final model" : "Median latency by final model"}
              right={
                <div className="seg">
                  {(["success", "cost", "latency"] as const).map((t) => (
                    <button key={t} aria-pressed={donutTab === t} onClick={() => setDonutTab(t)}>
                      {t === "success" ? "Success rate" : t === "cost" ? "Cost" : "Latency"}
                    </button>
                  ))}
                </div>
              }
            >
              {donutTab === "latency" ? (
                <div className="py-4">
                  <Bars
                    data={tiers.map((t) => ({ key: t.key, label: t.label, value: median(byTier[t.key]?.lat || []), color: tierColor(t.key) }))}
                    format={(v) => ms(v)}
                  />
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-8">
                  <Donut slices={slices} center={donutTab === "success" ? num(sliceTotal) : usd(sliceTotal, 4)} sub={donutTab === "success" ? "successful tasks" : "total cost"} />
                  <table className="min-w-[220px] flex-1 text-sm">
                    <tbody>
                      {slices.map((s) => (
                        <tr key={s.key}>
                          <td className="py-2.5">
                            <span className="mr-2.5 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: s.color }} />
                            {s.label}
                          </td>
                          <td className="py-2.5 text-right font-medium tabular-nums">{sliceTotal ? pct(s.value / sliceTotal, 0) : "—"}</td>
                          <td className="py-2.5 pl-6 text-right tabular-nums text-muted">{s.display}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card
              title="Performance Trends"
              subtitle={`${trendTab === "latency" ? "Median latency" : "Average cost"} per task, last ${DAYS} days`}
              right={
                <div className="seg">
                  {(["latency", "cost"] as const).map((t) => (
                    <button key={t} aria-pressed={trendTab === t} onClick={() => setTrendTab(t)}>
                      {t === "latency" ? "Latency (ms)" : "Cost (USD)"}
                    </button>
                  ))}
                </div>
              }
            >
              <LineChart
                points={series.map((s) => ({ label: s.label, value: trendTab === "latency" ? s.latency : s.costPerTask }))}
                format={trendTab === "latency" ? (v) => `${Math.round(v).toLocaleString()}` : (v) => `$${v.toFixed(v < 0.01 ? 4 : 3)}`}
                color={trendTab === "latency" ? "var(--t-medium)" : "var(--t-small)"}
              />
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card
              title="Recent Workloads"
              right={
                <Link href="/history" className="inline-flex items-center gap-1 text-sm font-medium text-accent-strong">
                  View all <Icon name="arrowRight" size={15} />
                </Link>
              }
            >
              {rows.length === 0 ? (
                <p className="text-sm text-muted">No workloads yet. Run one from the Playground or the Challenge.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Task</th>
                        <th>Model</th>
                        <th>Quality</th>
                        <th className="num">Latency</th>
                        <th className="num">Cost</th>
                        <th className="num">Time</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {(wl?.items || []).filter((w: any) => w.provider === o.provider).slice(0, 5).map((w: any) => (
                        <tr key={w.id}>
                          <td className="max-w-[260px]">
                            <div className="flex items-center gap-2">
                              <Icon name="doc" size={16} className="shrink-0 text-muted" />
                              <span className="truncate" title={w.task_text}>{w.task_text}</span>
                            </div>
                          </td>
                          <td><TierPill tier={w.final_tier} label={label(w.final_tier)} /></td>
                          <td className="whitespace-nowrap">
                            {w.status === "passed" ? (
                              <span className="inline-flex items-center gap-1 text-accent"><Icon name="check" size={15} />Passed</span>
                            ) : w.status === "failed" ? (
                              <span className="text-bad">✕ Failed</span>
                            ) : (
                              <span className="text-muted">{w.status}</span>
                            )}
                          </td>
                          <td className="num">{w.latency_ms ? `${(w.latency_ms / 1000).toFixed(1)}s` : "—"}</td>
                          <td className="num">{usd(w.cost_usd, w.cost_usd !== null && w.cost_usd < 0.001 ? 6 : 4)}</td>
                          <td className="num whitespace-nowrap text-muted">{ago(w.created_at)}</td>
                          <td>
                            <Link href={`/history/${w.id}`} aria-label="Open workload" className="text-muted hover:text-fg">
                              <Icon name="chevron" size={16} />
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <div className="min-w-0 space-y-5">
              <Card
                title="System Status"
                right={
                  <Link href="/settings" className="inline-flex items-center gap-1 text-sm font-medium text-accent-strong">
                    View details <Icon name="arrowRight" size={15} />
                  </Link>
                }
              >
                <div className="divide-y divide-border rounded-xl border border-border text-sm">
                  {[
                    ["Nebius Token Factory", o.sample_data ? "Mock provider" : "Online", o.sample_data ? "warn" : "ok", o.latency_ms_median ? `${ms(o.latency_ms_median)} median` : "—"],
                    ["NVIDIA Nemotron Models", models?.catalog_validated ? "Available" : models?.catalog_error ? "Unverified" : "Checking", models?.catalog_validated ? "ok" : "warn", tierStatus],
                    ["Evaluation Pipeline", "Deterministic", "ok", cfg?.code_execution_enabled ? "sandbox on" : "sandbox off"],
                  ].map(([name, state, tone, detail]) => (
                    <div key={name} className="flex items-center gap-3 px-4 py-3">
                      <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full bg-accent-strong" />
                      <span className="min-w-0 flex-1">{name}</span>
                      <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap" style={{ color: tone === "ok" ? "var(--accent)" : "var(--warn)" }}>
                        <span className="inline-block h-2 w-2 rounded-full" style={{ background: "currentColor" }} />
                        {state}
                      </span>
                      <span className="hidden shrink-0 whitespace-nowrap text-right text-muted sm:inline">{detail}</span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card title={<span>Environmental Impact <span className="text-sm font-normal text-muted">(Estimated)</span></span>}>
                {!env ? (
                  <p className="text-sm text-muted">
                    Run a benchmark with <code>fixed:large</code> and an adaptive condition to compare. <Link href="/benchmarks" className="underline">Benchmarks</Link>
                  </p>
                ) : (
                  <>
                    <div className="grid grid-cols-3 divide-x divide-border">
                      {[
                        ["leaf", env.energy, "energy use"],
                        ["drop", env.water, "water use"],
                        ["cloud", env.co2, "carbon impact"],
                      ].map(([icon, v, what]) => (
                        <div key={what as string} className="flex gap-2 px-3 first:pl-0">
                          <Icon name={icon as string} size={22} className="mt-1 shrink-0 text-accent" />
                          <div>
                            <div className="text-xl font-semibold tabular-nums">{v === null ? "—" : pct(Math.abs(v as number), 0)}</div>
                            <div className="text-xs leading-snug text-muted">
                              {(v as number) >= 0 ? "Lower" : "Higher"} estimated {what as string}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <p className="mt-3 text-xs text-muted">
                      <code>{env.routedKey}</code> vs fixed large-model baseline, latest benchmark, central scenario
                      {env.passDiff !== null && <> · pass rate {env.passDiff >= 0 ? "+" : ""}{(env.passDiff * 100).toFixed(0)} pts</>}.{" "}
                      <Link href="/methodology" className="underline">How this is estimated</Link>
                    </p>
                  </>
                )}
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
