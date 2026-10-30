"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ci, ms, num, pct, sci, signedCi, signedPct, usd, when } from "@/lib/format";
import { Badge, Bars, Card, ErrorBox, Loading, PageHeader, SampleBanner, TierBadge, statusTone } from "@/components/ui";

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function BenchmarkRun() {
  const { id } = useParams<{ id: string }>();
  const { data: run, error, reload } = useApi<any>(`/api/benchmarks/${id}`, { poll: true, intervalMs: 2500 });
  const active = run && ["queued", "running"].includes(run.status);
  const { data: wls } = useApi<any>(run && !active ? `/api/benchmarks/${id}/workloads` : null);
  const { data: impact } = useApi<any>(run && !active ? `/api/impact?run_id=${id}` : null);
  const summ = run?.summary;
  const conds: [string, any][] = summ ? Object.entries(summ.conditions) : [];

  async function cancel() {
    await apiPost(`/api/benchmarks/${id}/cancel`).catch(() => {});
    reload();
  }

  return (
    <div>
      <PageHeader
        title="Benchmark run"
        subtitle={run && `${when(run.created_at)} · ${run.dataset_version} · ${run.config?.split} split · provider ${run.provider}`}
        actions={
          <>
            <Link href="/benchmarks" className="btn">
              All runs
            </Link>
            {active && (
              <button className="btn" onClick={cancel}>
                Cancel
              </button>
            )}
            {run && !active && (
              <button className="btn" onClick={async () => download(`run-${id}-${run.provider}.json`, await apiGet(`/api/bundles/benchmark/${id}`))}>
                Export JSON
              </button>
            )}
          </>
        }
      />
      <ErrorBox error={error} />
      <SampleBanner show={run?.provider && run.provider !== "nebius"} />
      {!run && !error && <Loading />}
      {run && (
        <>
          <Card className="mb-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <Badge tone={statusTone(run.status)}>{run.status}</Badge>
              <span>
                {run.progress_done}/{run.progress_total} workloads · {run.calls_made} calls (cap {run.max_calls})
              </span>
              {run.error && <span className="text-bad">{run.error}</span>}
            </div>
            <div className="mt-2 h-2 rounded-full bg-panel-2">
              <div className="h-2 rounded-full bg-accent transition-all" style={{ width: `${(run.progress_done / Math.max(1, run.progress_total)) * 100}%` }} />
            </div>
          </Card>

          {summ && conds.length > 0 && (
            <>
              <Card title="Results by condition" className="mb-4">
                <div className="overflow-x-auto">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Condition</th>
                        <th className="num">n</th>
                        <th className="num">Pass rate</th>
                        <th className="num">95% CI (Wilson)</th>
                        <th className="num">Total cost</th>
                        <th className="num">$ / task</th>
                        <th className="num">$ / success</th>
                        <th className="num">Tokens / task</th>
                        <th className="num">Latency median · p95</th>
                        <th className="num">Calls / task</th>
                        <th className="num">Escalation</th>
                        <th>Final tiers</th>
                      </tr>
                    </thead>
                    <tbody>
                      {conds.map(([c, m]) => (
                        <tr key={c}>
                          <td>
                            <code>{c}</code>
                            {c === summ.baseline && (
                              <span className="ml-1">
                                <Badge>baseline</Badge>
                              </span>
                            )}
                          </td>
                          <td className="num">{m.n}</td>
                          <td className="num font-medium">{pct(m.success_rate)}</td>
                          <td className="num text-muted">{ci(m.success_ci95)}</td>
                          <td className="num">{m.cost_complete ? usd(m.total_cost_usd) : "—"}</td>
                          <td className="num">{usd(m.cost_per_task_usd)}</td>
                          <td className="num">{usd(m.cost_per_success_usd)}</td>
                          <td className="num">{num(m.tokens_per_task)}</td>
                          <td className="num">
                            {ms(m.latency_ms_median)}
                            <div className="text-xs text-muted">p95 {m.latency_ms_p95 != null ? ms(m.latency_ms_p95) : "n<20"}</div>
                          </td>
                          <td className="num">{num(m.calls_per_task, 2)}</td>
                          <td className="num">{pct(m.escalation_rate, 0)}</td>
                          <td className="text-xs">
                            {Object.entries(m.final_tier_distribution || {}).map(([t, k]: [string, any]) => (
                              <span key={t} className="mr-2">
                                <TierBadge tier={t} label={`${t} ${k}`} />
                              </span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {conds.some(([, m]) => !m.cost_complete) && (
                  <p className="mt-2 text-xs text-muted">Cost shows “—” when a price is not configured or a call did not report usage. Token counts are still provider-reported.</p>
                )}
              </Card>

              {Object.keys(summ.comparisons || {}).length > 0 && (
                <Card title={`Paired comparison vs ${summ.baseline} (bootstrap 95% CI)`} className="mb-4">
                  <div className="overflow-x-auto">
                    <table className="data">
                      <thead>
                        <tr>
                          <th>Condition</th>
                          <th className="num">Paired tasks</th>
                          <th>Per-task outcomes</th>
                          <th className="num">Δ pass rate</th>
                          <th className="num">Δ cost</th>
                          <th className="num">Δ $/success</th>
                          <th className="num">Δ tokens</th>
                          <th className="num">Δ latency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(summ.comparisons).map(([c, x]: [string, any]) => (
                          <tr key={c}>
                            <td>
                              <code>{c}</code>
                            </td>
                            <td className="num">{x.paired_tasks}</td>
                            <td className="text-xs">
                              {x.paired_outcomes ? (
                                <>
                                  {x.paired_outcomes.both_pass} both pass · {x.paired_outcomes.both_fail} both fail
                                  <div style={{ color: x.paired_outcomes.losses.length ? "var(--bad)" : "var(--muted)" }}>
                                    {x.paired_outcomes.losses.length} lost{x.paired_outcomes.losses.length ? `: ${x.paired_outcomes.losses.join(", ")}` : ""}
                                  </div>
                                  <div style={{ color: x.paired_outcomes.gains.length ? "var(--accent)" : "var(--muted)" }}>
                                    {x.paired_outcomes.gains.length} gained{x.paired_outcomes.gains.length ? `: ${x.paired_outcomes.gains.join(", ")}` : ""}
                                  </div>
                                </>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="num">
                              {signedPct(x.success_rate_diff)}
                              <div className="text-xs text-muted">{signedCi(x.success_rate_diff_ci95)}</div>
                            </td>
                            <td className="num">
                              {signedPct(x.cost_rel_change)}
                              <div className="text-xs text-muted">{signedCi(x.cost_rel_change_ci95)}</div>
                            </td>
                            <td className="num">{signedPct(x.cost_per_success_rel_change)}</td>
                            <td className="num">
                              {signedPct(x.tokens_rel_change)}
                              <div className="text-xs text-muted">{signedCi(x.tokens_rel_change_ci95)}</div>
                            </td>
                            <td className="num">
                              {signedPct(x.latency_mean_rel_change)}
                              <div className="text-xs text-muted">{signedCi(x.latency_rel_change_ci95)}</div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-xs text-muted">Equal pass rates do not mean equal quality: “lost” lists tasks that passed on the baseline and failed under this condition. Δ pass rate is in percentage points; other deltas are relative changes versus the baseline on the same tasks. A CI that crosses zero means the difference is not distinguishable at this sample size.</p>
                </Card>
              )}

              {conds.some(([, m]) => m.quality_failures?.length) && (
                <Card title="Quality failures" subtitle="Every task that did not pass its deterministic check, per condition. Open one to see the validator's reason." className="mb-4">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {conds.map(([c, m]) => (
                      <div key={c} className="rounded-2xl border border-border p-4">
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <code className="text-xs">{c}</code>
                          <Badge tone={m.quality_failures?.length ? "bad" : "good"}>{m.quality_failures?.length || 0} failed</Badge>
                        </div>
                        <ul className="space-y-1 text-xs">
                          {(m.quality_failures || []).map((f: any) => {
                            const w = wls?.items?.find((x: any) => x.case_id === f.case_id && x.condition === c && (x.repeat || 0) === (f.repeat || 0));
                            return (
                              <li key={`${f.case_id}-${f.repeat}`} className="flex items-center justify-between gap-2">
                                {w ? <Link className="underline" href={`/history/${w.id}`}>{f.case_id}</Link> : <span>{f.case_id}</span>}
                                <span className="text-muted">{f.category} · {f.status} · <TierBadge tier={f.final_tier} /></span>
                              </li>
                            );
                          })}
                          {!m.quality_failures?.length && <li className="text-muted">none</li>}
                        </ul>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Card title="Pass rate by category">
                  <div className="space-y-4">
                    {Object.entries(summ.by_category || {}).map(([c, cats]: [string, any]) => (
                      <div key={c}>
                        <div className="mb-1 text-xs font-medium">
                          <code>{c}</code>
                        </div>
                        <Bars data={Object.entries(cats).map(([cat, m]: [string, any]) => ({ key: cat, value: m.success_rate, note: `n=${m.n}` }))} format={(v) => pct(v, 0)} max={1} />
                      </div>
                    ))}
                  </div>
                </Card>
                <Card title="Estimated environmental impact (central scenario)">
                  {!impact ? (
                    <Loading />
                  ) : (
                    <>
                      <table className="data">
                        <thead>
                          <tr>
                            <th>Condition</th>
                            <th className="num">Energy</th>
                            <th className="num">CO₂e</th>
                            <th className="num">Water</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(impact.conditions || {}).map(([c, v]: [string, any]) => {
                            const s = v.estimated?.scenarios?.central;
                            return (
                              <tr key={c}>
                                <td>
                                  <code>{c}</code>
                                </td>
                                <td className="num">{sci(s?.energy_wh, "Wh")}</td>
                                <td className="num">{sci(s?.co2e_g, "g")}</td>
                                <td className="num">{sci(s?.water_ml, "mL")}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                      <p className="mt-2 text-xs text-muted">
                        Category B estimates from FLOPs ≈ 2 × active params × tokens, with stated assumptions. See <Link className="underline" href="/methodology">Methodology</Link> for low/high bounds.
                      </p>
                    </>
                  )}
                </Card>
              </div>
            </>
          )}

          {wls?.items && (
            <Card title={`Workloads (${wls.items.length})`}>
              <div className="max-h-[480px] overflow-auto">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Condition</th>
                      <th>Status</th>
                      <th>Path</th>
                      <th className="num">Tokens</th>
                      <th className="num">Latency</th>
                      <th className="num">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wls.items.map((w: any) => (
                      <tr key={w.id}>
                        <td>
                          <Link className="underline" href={`/history/${w.id}`}>
                            {w.case_id}
                          </Link>
                          {w.repeat > 0 && <span className="text-muted"> r{w.repeat}</span>}
                        </td>
                        <td>
                          <code className="text-xs">{w.condition}</code>
                        </td>
                        <td>
                          <Badge tone={statusTone(w.status)}>{w.status}</Badge>
                        </td>
                        <td className="text-xs">
                          {w.initial_tier !== w.final_tier ? (
                            <>
                              <TierBadge tier={w.initial_tier} /> → <TierBadge tier={w.final_tier} />
                            </>
                          ) : (
                            <TierBadge tier={w.final_tier} />
                          )}
                        </td>
                        <td className="num">{num((w.prompt_tokens || 0) + (w.completion_tokens || 0))}</td>
                        <td className="num">{ms(w.latency_ms)}</td>
                        <td className="num">{usd(w.cost_usd, 6)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
