"use client";

import Link from "next/link";
import { useApi } from "@/lib/useApi";
import { ms, pct, signedPct, usd, when } from "@/lib/format";
import HeroVisual from "@/components/HeroVisual";
import { BackendHint, Bars, Card, ErrorBox, Loading, SampleBanner, Stat, TierBadge, tierColor } from "@/components/ui";

export default function Overview() {
  const { data: o, error } = useApi<any>("/api/overview");
  const { data: cfg } = useApi<any>("/api/config");
  const labels: Record<string, string> = Object.fromEntries((cfg?.tiers || []).map((t: any) => [t.key, t.label]));
  const lb = o?.latest_benchmark;
  const summ = lb?.summary;
  const comps = summ?.comparisons ? Object.entries(summ.comparisons) : [];

  return (
    <div>
      <section className="relative mb-12 grid items-center gap-8 pt-4 lg:grid-cols-[1.15fr_1fr]">
        <div>
          <div className="eyebrow mb-4">NVIDIA Nemotron · Nebius Token Factory</div>
          <h1 className="text-6xl font-extralight leading-[0.95] tracking-tight md:text-8xl">
            Eco<span className="font-light text-accent">Compute</span>
          </h1>
          <p className="mt-4 text-2xl font-light tracking-tight md:text-3xl">The smallest model that gets it right.</p>
          <p className="mt-4 max-w-xl text-[15px] font-light leading-relaxed text-muted">
            Every task starts on the cheapest Nemotron likely to pass an objective quality check. If the check fails, EcoCompute escalates. Every decision, token and cent is recorded, so you can verify the savings yourself.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/challenge" className="btn btn-primary">
              Run the Challenge <span aria-hidden>→</span>
            </Link>
            <Link href="/playground" className="btn">
              Open Playground <span aria-hidden>▸</span>
            </Link>
          </div>
          {o && (
            <div className="mt-10 grid max-w-xl grid-cols-3 gap-6">
              {[
                [o.workloads_total, "", "workloads routed"],
                [o.quality_pass_rate != null ? (o.quality_pass_rate * 100).toFixed(0) : "—", o.quality_pass_rate != null ? "%" : "", "met quality"],
                [o.escalation_rate != null ? (o.escalation_rate * 100).toFixed(0) : "—", o.escalation_rate != null ? "%" : "", "needed escalation"],
              ].map(([v, unit, label]) => (
                <div key={label as string}>
                  <div className="text-3xl font-light tabular-nums md:text-4xl">
                    {v}
                    <span className="text-accent">{unit}</span>
                  </div>
                  <div className="mt-1 text-xs text-muted">{label}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex justify-center lg:justify-end">
          <HeroVisual />
        </div>
      </section>

      <ErrorBox error={error} hint={<BackendHint />} />
      <SampleBanner show={o?.sample_data} />
      {!o && !error && <Loading />}
      {o && (
        <>
          <div className="mb-6 flex items-end justify-between">
            <h2 className="text-3xl font-light tracking-tight">Driven by evidence, guided by quality</h2>
          </div>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Cost per success" value={usd(o.cost_per_success_usd)} hint={`total ${usd(o.total_cost_usd)}`} />
            <Stat label="Median latency" value={ms(o.latency_ms_median)} hint={`mean ${ms(o.latency_ms_mean)}`} />
            <Stat label="Graded workloads" value={o.workloads_graded} hint="checked by deterministic validators" />
            <Stat label="Spend today" value={usd(o.spend_today_usd, 4)} hint={`of ${usd(o.daily_budget_usd, 2)} daily budget`} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Latest benchmark" right={lb && <Link className="text-xs underline" href={`/benchmarks/${lb.id}`}>open</Link>}>
              {!lb && (
                <p className="text-sm text-muted">
                  No completed benchmark yet. Run one in the <Link className="underline" href="/benchmarks">Benchmark Lab</Link>.
                </p>
              )}
              {lb && (
                <div className="space-y-3">
                  <div className="text-xs text-muted">
                    {when(lb.created_at)} · {lb.status} · baseline <code>{summ.baseline}</code>
                  </div>
                  <Bars
                    data={Object.entries(summ.conditions).map(([c, m]: [string, any]) => ({
                      key: c,
                      value: m.success_rate,
                      note: `n=${m.n}`,
                    }))}
                    format={(v) => pct(v)}
                    max={1}
                  />
                  {comps.map(([c, cmp]: [string, any]) => (
                    <div key={c} className="rounded-xl bg-panel-2 p-3 text-sm">
                      <b>{c}</b> vs {summ.baseline}: success {signedPct(cmp.success_rate_diff)} · cost {signedPct(cmp.cost_rel_change)} · tokens{" "}
                      {signedPct(cmp.tokens_rel_change)} · latency {signedPct(cmp.latency_mean_rel_change)}
                      <span className="text-muted"> ({cmp.paired_tasks} paired tasks)</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Where workloads finished">
              {Object.keys(o.final_tier_distribution || {}).length === 0 ? (
                <p className="text-sm text-muted">No workloads yet.</p>
              ) : (
                <Bars
                  data={Object.entries(o.final_tier_distribution).map(([t, n]: [string, any]) => ({
                    key: t,
                    label: <TierBadge tier={t} label={labels[t]} />,
                    value: n,
                    color: tierColor(t),
                  }))}
                />
              )}
              {Object.keys(o.tier_by_category || {}).length > 0 && (
                <div className="mt-4 overflow-x-auto">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Category</th>
                      {(cfg?.tiers || []).map((t: any) => (
                        <th key={t.key} className="num">
                          {t.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(o.tier_by_category).map(([cat, row]: [string, any]) => (
                      <tr key={cat}>
                        <td>{cat}</td>
                        {(cfg?.tiers || []).map((t: any) => (
                          <td key={t.key} className="num">
                            {row[t.key] || 0}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
            </Card>
          </div>

          <h2 className="mb-6 mt-14 text-3xl font-light tracking-tight">Where efficiency meets proof</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {[
              ["Analyze", "Category, complexity and expected output size, with every rule that fired."],
              ["Select", "Cheapest start tier whose whole escalation chain still meets the quality target."],
              ["Execute", "Real Nebius call. Provider-reported tokens, latency, request ID and cost."],
              ["Evaluate", "Deterministic validators: schema, exact fields, numbers, terms, sandboxed tests."],
              ["Escalate & learn", "Only on a failed check. Everything is recorded and updates the evidence."],
            ].map(([t, d], k) => (
              <div key={t} className="card p-5">
                <div className="font-mono text-xs text-accent">0{k + 1}</div>
                <div className="mt-3 text-lg font-normal">{t}</div>
                <p className="mt-2 text-sm font-light leading-relaxed text-muted">{d}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
