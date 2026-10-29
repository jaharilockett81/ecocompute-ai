"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiBase, apiGet, streamChallenge, type TraceEvent } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ms, num, signedPct, usd, when } from "@/lib/format";
import TraceView from "@/components/TraceView";
import { Badge, Card, ErrorBox, PageHeader, SampleBanner, TierBadge } from "@/components/ui";

type Lane = "ecocompute" | "baseline";
type StepState = "done" | "pending" | "skipped" | "failed";

const OUTCOME_LABEL: Record<string, string> = {
  first_attempt_pass: "Passed on first attempt",
  escalated_then_passed: "Escalated, then passed",
  escalated_still_failed: "Escalated, still failed",
  failed_no_escalation: "Failed (no escalation left)",
};

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** The eight things a judge should see, derived only from the streamed trace and the final record. */
function checklist(eco: TraceEvent[], base: TraceEvent[], started: boolean, result: any, tierRank: Record<string, number>, baselineTier: string) {
  const sel = eco.find((e) => e.step === "select");
  const evals = eco.filter((e) => e.step === "evaluate" && e.status !== "running");
  const failedEval = evals.find((e) => e.status === "failed");
  const escalated = eco.some((e) => e.step === "escalate");
  const ecoDone = eco.some((e) => e.step === "final" && e.data?.status);
  const baseDone = base.some((e) => e.step === "final" && e.data?.status);
  const firstPassed = evals[0]?.status === "done";
  const startTier = sel?.data?.start_tier;
  const smaller = startTier != null && (tierRank[startTier] ?? 99) < (tierRank[baselineTier] ?? -1);
  const items: [string, StepState, string][] = [
    ["Task submitted with a defined quality requirement", started ? "done" : "pending", ""],
    ["Routing policy selects a smaller model", !sel ? "pending" : smaller ? "done" : "failed", sel ? `started on ${startTier}` : ""],
    ["Validator detects an inadequate result", failedEval ? "done" : firstPassed ? "skipped" : "pending", failedEval ? failedEval.detail?.slice(0, 90) || "" : firstPassed ? "not needed: first answer passed" : ""],
    ["Automatic escalation to a more capable model", escalated ? "done" : firstPassed || (ecoDone && !escalated) ? "skipped" : "pending", escalated ? "" : firstPassed ? "not needed" : ""],
    ["Final answer checked against the same requirement", ecoDone && evals.length ? (evals[evals.length - 1].status === "done" ? "done" : "failed") : "pending", ecoDone && evals.length ? (evals[evals.length - 1].status === "done" ? "passed" : "did not pass") : ""],
    ["Complete decision trace displayed", ecoDone ? "done" : "pending", ""],
    ["Fixed-model baseline runs the same workload", baseDone ? "done" : base.length ? "pending" : "pending", baseDone ? `on ${baselineTier}` : ""],
    ["Quality, latency, tokens and cost compared", result ? "done" : "pending", ""],
  ];
  return items;
}

function Icon({ s }: { s: StepState }) {
  const map = { done: ["✓", "var(--accent)"], failed: ["✕", "var(--bad)"], skipped: ["–", "var(--muted)"], pending: ["○", "var(--muted)"] } as const;
  return (
    <span className="inline-block w-4 text-center font-semibold" style={{ color: map[s][1] }}>
      {map[s][0]}
    </span>
  );
}

function Delta({ v, lowerIsBetter = true }: { v: number | null | undefined; lowerIsBetter?: boolean }) {
  if (v === null || v === undefined) return <span className="text-muted">—</span>;
  const good = lowerIsBetter ? v < 0 : v > 0;
  return <span style={{ color: v === 0 ? "var(--muted)" : good ? "var(--accent)" : "var(--bad)" }}>{signedPct(v, 0)}</span>;
}

export default function ChallengePage() {
  const { data: sc, error: scErr } = useApi<any>("/api/challenge/scenarios");
  const { data: cfg } = useApi<any>("/api/config");
  const { data: past, reload: reloadPast } = useApi<any>("/api/challenges");
  const [lanes, setLanes] = useState<Record<Lane, TraceEvent[]>>({ ecocompute: [], baseline: [] });
  const [running, setRunning] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const tierRank: Record<string, number> = useMemo(() => Object.fromEntries((cfg?.tiers || []).map((t: any) => [t.key, t.rank])), [cfg]);
  const tierLabel = (k?: string | null) => cfg?.tiers?.find((t: any) => t.key === k)?.label || k || "—";
  const baselineTier = cfg?.baseline_tier || "large";
  const cmp = result?.comparison;

  async function run(id: string) {
    setError(null);
    setResult(null);
    setStarted(false);
    setLanes({ ecocompute: [], baseline: [] });
    setRunning(id);
    window.history.replaceState(null, "", "/challenge");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const done = await streamChallenge(
        id,
        (e) => {
          if (e.step === "challenge") setStarted(true);
          else if (e.lane === "ecocompute" || e.lane === "baseline") setLanes((l) => ({ ...l, [e.lane as Lane]: [...l[e.lane as Lane], e] }));
        },
        ac.signal,
      );
      setResult(done);
      window.history.replaceState(null, "", `/challenge?id=${done.id}`);
      reloadPast();
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setRunning(null);
    }
  }

  async function load(cid: string) {
    setError(null);
    try {
      const c = await apiGet(`/api/challenges/${cid}`);
      const [eco, base] = await Promise.all([
        c.ecocompute_workload_id ? apiGet(`/api/workloads/${c.ecocompute_workload_id}`) : null,
        c.baseline_workload_id ? apiGet(`/api/workloads/${c.baseline_workload_id}`) : null,
      ]);
      setLanes({ ecocompute: eco?.trace || [], baseline: base?.trace || [] });
      setStarted(true);
      setResult(c);
      window.history.replaceState(null, "", `/challenge?id=${cid}`);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) load(id);
  }, []);

  const items = checklist(lanes.ecocompute, lanes.baseline, started, result, tierRank, baselineTier);
  const activeScenario = sc?.scenarios?.find((s: any) => s.id === (running || cmp?.scenario?.id));
  const eco = cmp?.lanes?.ecocompute;
  const base = cmp?.lanes?.baseline;

  return (
    <div>
      <PageHeader
        title="The EcoCompute Challenge"
        subtitle="One task, two lanes, real inference. EcoCompute routes the task to the cheapest model likely to pass an objective check and escalates only if the check fails. A fixed baseline runs the same task on the largest model. Then we compare what actually happened."
      />
      <SampleBanner show={sc?.sample_data} />
      <ErrorBox
        error={scErr || error}
        hint={error?.includes("access code") ? <span>Enter it in <Link className="underline" href="/settings">Settings</Link>.</span> : undefined}
      />

      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        {sc?.scenarios?.map((s: any) => (
          <Card
            key={s.id}
            title={s.title}
            right={<Badge tone={s.kind === "first_attempt" ? "good" : "warn"}>{s.kind === "first_attempt" ? "routine" : "escalation-prone"}</Badge>}
          >
            <p className="text-sm">{s.blurb}</p>
            <p className="mt-2 text-xs text-muted">
              <b className="text-fg">Quality requirement:</b> {s.requirement}
            </p>
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer text-muted">Show task</summary>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-panel-2 p-2">{s.task}</pre>
            </details>
            <div className="mt-3 flex items-center gap-3">
              <button className="btn btn-primary" disabled={!!running} onClick={() => run(s.id)}>
                {running === s.id ? "Running both lanes…" : "Run live"}
              </button>
              <span className="text-xs text-muted">
                vs fixed <TierBadge tier={s.baseline.tier} label={s.baseline.label} />
              </span>
            </div>
          </Card>
        ))}
      </div>
      <p className="-mt-2 mb-4 text-xs text-muted">
        Nothing is scripted: both lanes make genuine calls with temperature 0, and escalation happens only when the validator rejects a real answer. If the small model succeeds on the hard task, that is what you will see.
      </p>

      {(started || running) && (
        <>
          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Card title="What a judge should see" right={activeScenario && <span className="text-xs text-muted">{activeScenario.title}</span>}>
              <ol className="space-y-1.5 text-sm">
                {items.map(([label, st, note], i) => (
                  <li key={i} className="flex gap-2">
                    <Icon s={st} />
                    <span className={st === "pending" ? "text-muted" : ""}>
                      {i + 1}. {label}
                      {note && <span className="block text-xs text-muted">{note}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            </Card>

            <Card title="Result">
              {!cmp ? (
                <p className="text-sm text-muted">{running ? "Both lanes are running…" : "No result."}</p>
              ) : (
                <div className="space-y-3">
                  <div className={`rounded-xl p-3 text-sm font-medium ${cmp.improved ? "bg-accent-soft text-accent" : "bg-warn-soft text-warn"}`}>{cmp.verdict}</div>
                  <p className="text-sm">{cmp.what_happened}</p>
                  <div className="overflow-x-auto">
                    <table className="data">
                      <thead>
                        <tr>
                          <th></th>
                          <th className="num">EcoCompute</th>
                          <th className="num">Fixed {tierLabel(cmp.baseline_tier)}</th>
                          <th className="num">Change</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>Quality requirement</td>
                          <td className="num">{eco.passed ? <Badge tone="good">met</Badge> : <Badge tone="bad">not met</Badge>}</td>
                          <td className="num">{base.passed ? <Badge tone="good">met</Badge> : <Badge tone="bad">not met</Badge>}</td>
                          <td className="num text-xs text-muted">{eco.passed === base.passed ? "same" : eco.passed ? "better" : "worse"}</td>
                        </tr>
                        <tr>
                          <td>Path</td>
                          <td className="num text-xs">
                            {eco.initial_tier !== eco.final_tier ? `${tierLabel(eco.initial_tier)} → ${tierLabel(eco.final_tier)}` : tierLabel(eco.final_tier)}
                            <div className="text-muted">{OUTCOME_LABEL[eco.outcome] || eco.outcome}</div>
                          </td>
                          <td className="num text-xs">{tierLabel(base.final_tier)}</td>
                          <td></td>
                        </tr>
                        <tr>
                          <td>Model calls</td>
                          <td className="num">{eco.calls}</td>
                          <td className="num">{base.calls}</td>
                          <td></td>
                        </tr>
                        <tr>
                          <td>Total tokens</td>
                          <td className="num">
                            {num(eco.total_tokens)}
                            {eco.reasoning_tokens ? <div className="text-xs text-muted">{num(eco.reasoning_tokens)} reasoning</div> : null}
                          </td>
                          <td className="num">
                            {num(base.total_tokens)}
                            {base.reasoning_tokens ? <div className="text-xs text-muted">{num(base.reasoning_tokens)} reasoning</div> : null}
                          </td>
                          <td className="num">
                            <Delta v={cmp.deltas.tokens_rel} />
                          </td>
                        </tr>
                        <tr>
                          <td>Model latency</td>
                          <td className="num">{ms(eco.model_latency_ms)}</td>
                          <td className="num">{ms(base.model_latency_ms)}</td>
                          <td className="num">
                            <Delta v={cmp.deltas.model_latency_rel} />
                          </td>
                        </tr>
                        <tr>
                          <td>End-to-end latency</td>
                          <td className="num">{ms(eco.wall_ms)}</td>
                          <td className="num">{ms(base.wall_ms)}</td>
                          <td className="num">
                            <Delta v={cmp.deltas.wall_latency_rel} />
                          </td>
                        </tr>
                        <tr>
                          <td>Inference cost</td>
                          <td className="num">{usd(eco.inference_cost_usd, 6)}</td>
                          <td className="num">{usd(base.inference_cost_usd, 6)}</td>
                          <td></td>
                        </tr>
                        <tr>
                          <td>
                            Routing overhead
                            <div className="text-xs text-muted">rule-based, no model call</div>
                          </td>
                          <td className="num">
                            $0 · {eco.overhead.routing_ms.toFixed(1)} ms
                          </td>
                          <td className="num text-muted">n/a</td>
                          <td></td>
                        </tr>
                        <tr>
                          <td>
                            Evaluation overhead
                            <div className="text-xs text-muted">deterministic validators</div>
                          </td>
                          <td className="num">
                            {usd(eco.overhead.overhead_cost_usd, 6)} · {eco.overhead.evaluation_ms.toFixed(1)} ms
                          </td>
                          <td className="num">
                            {usd(base.overhead.overhead_cost_usd, 6)} · {base.overhead.evaluation_ms.toFixed(1)} ms
                          </td>
                          <td></td>
                        </tr>
                        <tr className="font-medium">
                          <td>Total cost</td>
                          <td className="num">{usd(eco.total_cost_usd, 6)}</td>
                          <td className="num">{usd(base.total_cost_usd, 6)}</td>
                          <td className="num">
                            <Delta v={cmp.deltas.cost_rel} />
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Card>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card title={<span>EcoCompute lane <span className="font-normal text-muted">· routed</span></span>} right={running && <Badge tone="info">live</Badge>}>
              {lanes.ecocompute.length ? <TraceView events={lanes.ecocompute} live={!!running} /> : <p className="text-sm text-muted">Waiting…</p>}
            </Card>
            <Card title={<span>Baseline lane <span className="font-normal text-muted">· fixed {tierLabel(baselineTier)}, no escalation</span></span>} right={running && <Badge tone="info">live</Badge>}>
              {lanes.baseline.length ? <TraceView events={lanes.baseline} live={!!running} /> : <p className="text-sm text-muted">Waiting…</p>}
            </Card>
          </div>

          {cmp && (
            <Card
              title="Verify it yourself"
              className="mb-4"
              right={
                <button className="btn" onClick={() => download(`ecocompute-challenge-${result.id}.json`, result)}>
                  Export JSON
                </button>
              }
            >
              <p className="mb-2 text-sm">
                Every call below was made to <b>{cmp.provider}</b>. Request IDs, model names and token counts are what the provider returned. The raw records are public JSON:
              </p>
              <ul className="mb-3 space-y-1 text-xs">
                {[
                  ["Challenge record", `/api/challenges/${result.id}`],
                  ["EcoCompute workload", `/api/workloads/${eco.workload_id}`],
                  ["Baseline workload", `/api/workloads/${base.workload_id}`],
                ].map(([label, path]) => (
                  <li key={path}>
                    {label}:{" "}
                    <a className="font-mono underline" href={apiBase() + path} target="_blank" rel="noreferrer">
                      {path}
                    </a>
                  </li>
                ))}
              </ul>
              <div className="overflow-x-auto">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Lane</th>
                      <th>Tier</th>
                      <th>Model (as reported)</th>
                      <th>Request ID</th>
                      <th className="num">Tokens in / out</th>
                      <th className="num">Latency</th>
                      <th className="num">Cost</th>
                      <th>Validator</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(["ecocompute", "baseline"] as Lane[]).flatMap((ln) =>
                      cmp.lanes[ln].call_log.map((c: any, i: number) => {
                        return (
                          <tr key={`${ln}-${i}`}>
                            <td>{ln}</td>
                            <td>
                              <TierBadge tier={c.tier} />
                            </td>
                            <td>
                              <code className="text-xs">{c.model}</code>
                              {c.provider !== "nebius" && (
                                <span className="ml-1">
                                  <Badge tone="warn">{c.provider}</Badge>
                                </span>
                              )}
                            </td>
                            <td>
                              <code className="text-xs">{c.request_id || "—"}</code>
                            </td>
                            <td className="num">
                              {num(c.prompt_tokens)} / {num(c.completion_tokens)}
                            </td>
                            <td className="num">{ms(c.latency_ms)}</td>
                            <td className="num">{usd(c.cost_usd, 6)}</td>
                            <td>{c.validator_passed === true ? <Badge tone="good">pass</Badge> : c.validator_passed === false ? <Badge tone="bad">fail</Badge> : "—"}</td>
                          </tr>
                        );
                      }),
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}

      <Card title="Previous runs">
        {!past?.items?.length ? (
          <p className="text-sm text-muted">No runs yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="data">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Scenario</th>
                  <th>EcoCompute outcome</th>
                  <th className="num">Δ cost</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {past.items.map((c: any) => (
                  <tr key={c.id}>
                    <td className="whitespace-nowrap">
                      <button className="underline" onClick={() => load(c.id)}>
                        {when(c.created_at)}
                      </button>
                      {c.provider !== "nebius" && (
                        <span className="ml-1">
                          <Badge tone="warn">{c.provider}</Badge>
                        </span>
                      )}
                    </td>
                    <td>{c.comparison?.scenario?.title || c.scenario_id}</td>
                    <td className="text-xs">{c.comparison ? OUTCOME_LABEL[c.comparison.lanes.ecocompute.outcome] || c.comparison.lanes.ecocompute.outcome : c.status}</td>
                    <td className="num">
                      <Delta v={c.comparison?.deltas?.cost_rel} />
                    </td>
                    <td className="max-w-md text-xs">{c.comparison?.verdict || c.error || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
