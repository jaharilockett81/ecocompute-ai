"use client";

import Link from "next/link";
import { useApi } from "@/lib/useApi";
import { ms, num, sci, usd } from "@/lib/format";
import { Badge, BackendHint, Bars, Card, ErrorBox, KV, Loading, PageHeader, SampleBanner, TierBadge, tierColor } from "@/components/ui";

const SCEN = ["low", "central", "high"] as const;

export default function ImpactPage() {
  const { data, error } = useApi<any>("/api/impact");
  const m = data?.measured;
  const e = data?.estimated;

  return (
    <div>
      <PageHeader
        title="Impact"
        subtitle="Three honest categories: A is what the API measures directly, B is a transparent physics-based estimate with low/central/high scenarios, and C is what cannot be observed from outside the data center."
      />
      <ErrorBox error={error} hint={<BackendHint />} />
      <SampleBanner show={data?.sample_data} />
      {!data && !error && <Loading />}
      {data && (
        <div className="space-y-4">
          <Card title="A · Directly measured" right={<Badge tone="good">measured</Badge>}>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <KV
                rows={[
                  ["Calls", `${num(m.calls)} (${num(m.failed_calls)} failed)`],
                  ["Workloads", num(m.workloads)],
                  ["Prompt tokens", num(m.prompt_tokens)],
                  ["Completion tokens", `${num(m.completion_tokens)}${m.reasoning_tokens ? ` (incl. ${num(m.reasoning_tokens)} reasoning)` : ""}`],
                  ["Total API latency", ms(m.total_latency_ms)],
                  ["Total cost", usd(m.total_cost_usd)],
                  ["Calls missing usage", num(m.calls_missing_usage)],
                ]}
              />
              <div>
                <div className="mb-2 text-xs text-muted">Calls by tier</div>
                {Object.keys(m.calls_by_tier || {}).length ? (
                  <Bars
                    data={Object.entries(m.calls_by_tier).map(([t, n]: [string, any]) => ({ key: t, label: <TierBadge tier={t} />, value: n, color: tierColor(t) }))}
                  />
                ) : (
                  <p className="text-sm text-muted">No calls yet.</p>
                )}
              </div>
            </div>
            <p className="mt-3 text-xs text-muted">Cost = provider-reported tokens × configured price per million tokens.</p>
          </Card>

          <Card title="B · Model-derived estimate" right={<Badge tone="warn">estimate, not a measurement</Badge>} className="border-dashed">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {SCEN.map((s) => (
                <div key={s} className={`rounded-xl p-3 ${s === "central" ? "bg-accent-soft" : "bg-panel-2"}`}>
                  <div className="text-xs uppercase tracking-wide text-muted">{s}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums">{sci(e.scenarios[s]?.energy_wh, "Wh")}</div>
                  <div className="text-sm tabular-nums">{sci(e.scenarios[s]?.co2e_g, "g CO₂e")}</div>
                  <div className="text-sm tabular-nums">{sci(e.scenarios[s]?.water_ml, "mL water")}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-muted">
              {e.calls_estimated} calls estimated, {e.calls_not_estimable} not estimable (missing usage or unknown active parameters; counted, never guessed). Low and high bounds differ by orders of magnitude because the inputs are genuinely uncertain.
            </p>
          </Card>

          <MatchedComparison />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card title="C · Not observable through the API" right={<Badge>not observable</Badge>}>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {data.methodology.not_observable.map((x: string) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </Card>
            <Card title="Why not latency × GPU power?">
              <p className="text-sm">{data.methodology.why_not_latency}</p>
              <p className="mt-2 text-sm">
                Full equations, scenario parameters and sources are on the <Link className="underline" href="/methodology">Methodology</Link> page.
              </p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

/** Baseline vs adaptive on the SAME tasks, only from a completed benchmark that ran both. */
function MatchedComparison() {
  const { data: runs } = useApi<any>("/api/benchmarks");
  const run = runs?.items?.find((r: any) => ["completed", "budget_stopped"].includes(r.status) && r.conditions?.includes("fixed:large") && r.conditions.some((c: string) => c.startsWith("adaptive")));
  const { data: imp } = useApi<any>(run ? `/api/impact?run_id=${run.id}` : null);
  const conds = imp ? Object.entries(imp.conditions || {}) : [];
  return (
    <Card title="Fixed baseline vs adaptive routing" subtitle={run ? `Matched tasks from benchmark run ${run.id} (${run.provider}). Cost and tokens are measured; energy, carbon and water are central estimates with low–high range.` : undefined} right={run && <Badge tone={run.provider === "nebius" ? "good" : "warn"}>{run.provider === "nebius" ? "real run" : "sample data"}</Badge>}>
      {!run ? (
        <p className="text-sm text-muted">
          Shown once a benchmark that ran <code>fixed:large</code> and an adaptive condition on the same tasks has completed. <Link className="underline" href="/benchmarks">Benchmarks</Link>
        </p>
      ) : !imp ? (
        <Loading />
      ) : (
        <div className="overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                <th>Condition</th>
                <th className="num">Tasks</th>
                <th className="num">Cost (measured)</th>
                <th className="num">Tokens (measured)</th>
                <th className="num">Energy (estimate)</th>
                <th className="num">CO₂e (estimate)</th>
              </tr>
            </thead>
            <tbody>
              {conds.map(([c, v]: [string, any]) => {
                const sc = v.estimated?.scenarios || {};
                return (
                  <tr key={c}>
                    <td><code>{c}</code></td>
                    <td className="num">{num(v.measured?.workloads)}</td>
                    <td className="num">{usd(v.measured?.total_cost_usd)}</td>
                    <td className="num">{num((v.measured?.prompt_tokens || 0) + (v.measured?.completion_tokens || 0))}</td>
                    <td className="num">
                      {sci(sc.central?.energy_wh, "Wh")}
                      <div className="text-xs text-muted">{sci(sc.low?.energy_wh, "")}–{sci(sc.high?.energy_wh, "Wh")}</div>
                    </td>
                    <td className="num">
                      {sci(sc.central?.co2e_g, "g")}
                      <div className="text-xs text-muted">{sci(sc.low?.co2e_g, "")}–{sci(sc.high?.co2e_g, "g")}</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
