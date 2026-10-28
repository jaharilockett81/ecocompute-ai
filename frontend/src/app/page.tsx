"use client";

import Link from "next/link";
import { useApi } from "@/lib/useApi";
import { ms, pct, signedPct, usd, when } from "@/lib/format";
import { BackendHint, Bars, Card, ErrorBox, Loading, PageHeader, SampleBanner, Stat, TierBadge, tierColor } from "@/components/ui";

export default function Overview() {
  const { data: o, error } = useApi<any>("/api/overview");
  const { data: cfg } = useApi<any>("/api/config");
  const labels: Record<string, string> = Object.fromEntries((cfg?.tiers || []).map((t: any) => [t.key, t.label]));
  const lb = o?.latest_benchmark;
  const summ = lb?.summary;
  const comps = summ?.comparisons ? Object.entries(summ.comparisons) : [];

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle="EcoCompute routes each task to the smallest NVIDIA Nemotron model on Nebius Token Factory that is likely to pass a deterministic quality gate, and escalates only when the gate actually fails."
        actions={
          <Link href="/playground" className="btn btn-primary">
            Try a workload
          </Link>
        }
      />
      <ErrorBox error={error} hint={<BackendHint />} />
      <SampleBanner show={o?.sample_data} />
      {!o && !error && <Loading />}
      {o && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Workloads" value={o.workloads_total} hint={`${o.workloads_graded} objectively graded`} />
            <Stat label="Quality pass rate" value={pct(o.quality_pass_rate)} hint="graded workloads only" />
            <Stat label="Cost per success" value={usd(o.cost_per_success_usd)} hint={`total ${usd(o.total_cost_usd)}`} />
            <Stat label="Escalation rate" value={pct(o.escalation_rate)} hint={`median latency ${ms(o.latency_ms_median)}`} />
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
                    <div key={c} className="rounded-lg bg-panel-2 p-3 text-sm">
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

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card title="How it works" className="lg:col-span-2">
              <ol className="list-decimal space-y-1 pl-5 text-sm">
                <li><b>Analyze</b> the task: category, complexity, expected output size.</li>
                <li><b>Select</b> the start tier with the lowest expected cost of the whole escalation chain, given Beta-posterior pass probabilities per category and tier.</li>
                <li><b>Execute</b> on Nebius Token Factory and record provider-reported tokens, latency and cost.</li>
                <li><b>Evaluate</b> with deterministic validators (JSON schema, exact fields, required terms, word limits, sandboxed tests).</li>
                <li><b>Repair or escalate</b> only when the gate fails; <b>record</b> everything; <b>learn</b> from the outcome.</li>
              </ol>
            </Card>
            <Card title="Spend guardrail">
              <div className="text-2xl font-semibold tabular-nums">{usd(o.spend_today_usd, 4)}</div>
              <div className="text-xs text-muted">of {usd(o.daily_budget_usd, 2)} daily budget</div>
              <div className="mt-2 h-2 rounded-full bg-panel-2">
                <div
                  className="h-2 rounded-full bg-accent"
                  style={{ width: `${Math.min(100, ((o.spend_today_usd || 0) / (o.daily_budget_usd || 1)) * 100)}%` }}
                />
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
