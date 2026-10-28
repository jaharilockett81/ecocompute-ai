"use client";

import Link from "next/link";
import { useApi } from "@/lib/useApi";
import { ms, num, sci, usd } from "@/lib/format";
import { BackendHint, Bars, Card, ErrorBox, KV, Loading, PageHeader, SampleBanner, TierBadge, tierColor } from "@/components/ui";

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
          <Card title="A · Directly measured">
            <div className="grid gap-4 md:grid-cols-2">
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

          <Card title="B · Model-derived estimate">
            <div className="grid gap-3 md:grid-cols-3">
              {SCEN.map((s) => (
                <div key={s} className={`rounded-lg p-3 ${s === "central" ? "bg-accent-soft" : "bg-panel-2"}`}>
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

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="C · Not observable through the API">
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
