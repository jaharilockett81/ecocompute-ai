"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiGet, apiPost, streamOptimize } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ms, num, pct, sci, signedPct, usd, when } from "@/lib/format";
import { Badge, Card, ErrorBox, Loading, PageHeader, SampleBanner, TierBadge } from "@/components/ui";
import Icon from "@/components/Icon";

const STEPS = ["Workload", "Baseline", "Analysis", "Review", "Verify", "Results", "Decision"];

function stepOf(st: any): number {
  if (!st) return 0;
  switch (st.status) {
    case "created":
    case "baseline_running":
      return 1;
    case "baseline_done":
    case "analysis_running":
    case "analysis_failed":
      return 2;
    case "proposed":
      return 3;
    case "verify_running":
      return 4;
    case "awaiting_approval":
    case "rejected":
      return 7;
    case "accepted":
    case "declined":
      return 8;
    default:
      return 1;
  }
}

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function describe(p: any): string {
  const cat = p.category === "*" ? "all categories" : p.category;
  if (p.type === "route_category") return `Route ${cat} to the ${p.tier} tier`;
  if (p.type === "cap_output_tokens") return `Cap ${cat} at ${p.max_output_tokens} output tokens`;
  if (p.type === "enable_escalation") return `${p.enabled ? "Enable" : "Disable"} escalation for ${cat}`;
  return `${p.type} (${cat})`;
}

function Stepper({ current, done }: { current: number; done: number }) {
  return (
    <ol className="mb-8 flex items-start overflow-x-auto pb-1" aria-label="Optimization progress">
      {STEPS.map((s, i) => {
        const n = i + 1;
        const state = n < done ? "done" : n === current ? "current" : "todo";
        return (
          <li key={s} className="flex min-w-[68px] flex-1 flex-col items-center" aria-current={state === "current" ? "step" : undefined}>
            <div className="flex w-full items-center">
              <span className={`h-px flex-1 ${i === 0 ? "opacity-0" : n <= done ? "bg-accent" : "bg-border-strong"}`} />
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold transition-colors ${
                  state === "done" ? "bg-accent-strong text-accent-ink" : state === "current" ? "bg-accent-strong text-accent-ink ring-4 ring-accent-soft" : "border border-border-strong bg-panel text-muted"
                }`}
              >
                {state === "done" ? "✓" : n}
              </span>
              <span className={`h-px flex-1 ${i === STEPS.length - 1 ? "opacity-0" : n < done ? "bg-accent" : "bg-border-strong"}`} />
            </div>
            <span className={`mt-2 text-xs ${state === "todo" ? "text-muted" : "font-medium text-fg"}`}>{s}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Before/after pair for one metric, on a shared scale. */
function Pair({ label, base, cand, fmt, lowerIsBetter = true }: { label: string; base: number | null | undefined; cand: number | null | undefined; fmt: (v: number) => string; lowerIsBetter?: boolean }) {
  const max = Math.max(1e-12, base ?? 0, cand ?? 0);
  const rel = base && cand != null ? cand / base - 1 : null;
  const good = rel == null ? null : lowerIsBetter ? rel < 0 : rel > 0;
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        {rel != null && <span style={{ color: rel === 0 ? "var(--muted)" : good ? "var(--accent)" : "var(--bad)" }} className="tabular-nums text-sm font-semibold">{signedPct(rel, 0)}</span>}
      </div>
      {[
        ["Baseline", base, "var(--muted)"],
        ["Optimized", cand, "var(--accent)"],
      ].map(([k, v, c]) => (
        <div key={k as string} className="mb-1 grid grid-cols-[72px_1fr_88px] items-center gap-2 text-xs">
          <span className="text-muted">{k as string}</span>
          <div className="h-2.5 rounded-full bg-panel-2">
            <div className="h-2.5 rounded-full" style={{ width: `${Math.max(1, ((v as number) ?? 0) / max * 100)}%`, background: c as string }} />
          </div>
          <span className="text-right tabular-nums">{v == null ? "—" : fmt(v as number)}</span>
        </div>
      ))}
    </div>
  );
}

function GateChecks({ gate }: { gate: any }) {
  return (
    <ul className="space-y-1.5 text-sm">
      {gate.checks.map((c: any) => (
        <li key={c.name} className="flex gap-2">
          <span className="w-4 shrink-0 text-center font-semibold" style={{ color: c.passed ? "var(--accent)" : "var(--bad)" }}>{c.passed ? "✓" : "✕"}</span>
          <span>
            {c.name}
            <span className="block text-xs text-muted">{c.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Totals({ t, e }: { t: any; e?: any }) {
  const cells: [string, string][] = [
    ["Quality", `${t.passed}/${t.tasks} passed`],
    ["Cost", usd(t.cost_usd)],
    ["Tokens", num(t.total_tokens)],
    ["Model time", ms(t.model_latency_ms)],
    ["Wall time", ms(t.wall_ms)],
    ["Backend CPU", ms(t.backend_cpu_ms)],
    ["Model calls", num(t.calls)],
    ["Energy (est.)", sci(e?.scenarios?.central?.energy_wh, "Wh")],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cells.map(([k, v]) => (
        <div key={k} className="rounded-xl bg-panel-2 px-3 py-2.5">
          <div className="text-xs text-muted">{k}</div>
          <div className="text-base font-semibold tabular-nums">{v}</div>
        </div>
      ))}
    </div>
  );
}

function RunTable({ base, cand }: { base: any; cand?: any }) {
  const c = new Map<string, any>((cand?.rows || []).map((r: any) => [r.case_id, r]));
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="data">
        <thead>
          <tr>
            <th>Task</th>
            <th>Category</th>
            <th>Baseline</th>
            {cand && <th>Optimized</th>}
            <th className="num">Tokens</th>
            {cand && <th className="num">Optimized tokens</th>}
          </tr>
        </thead>
        <tbody>
          {base.rows.map((r: any) => {
            const o = c.get(r.case_id);
            const regressed = o && r.passed && !o.passed;
            return (
              <tr key={r.case_id} className={regressed ? "bg-bad-soft" : ""}>
                <td>
                  <Link className="underline" href={`/history/${r.workload_id}`}>{r.case_id}</Link>
                </td>
                <td className="text-xs">{r.category}</td>
                <td className="text-xs">
                  <Badge tone={r.passed ? "good" : "bad"}>{r.passed ? "pass" : "fail"}</Badge> <TierBadge tier={r.final_tier} />
                </td>
                {cand && (
                  <td className="text-xs">
                    {o ? (
                      <>
                        <Badge tone={o.passed ? "good" : "bad"}>{o.passed ? "pass" : "fail"}</Badge> <TierBadge tier={o.final_tier} />
                        {o.escalations > 0 && <span className="ml-1 text-muted">escalated</span>}
                        {regressed && <div className="mt-0.5 text-bad">{o.eval_detail?.slice(0, 90) || o.status}</div>}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                )}
                <td className="num">{num(r.prompt_tokens + r.completion_tokens)}</td>
                {cand && <td className="num">{o ? num(o.prompt_tokens + o.completion_tokens) : "—"}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function WorkloadPicker({ onCreate, busy }: { onCreate: (body: any) => void; busy: boolean }) {
  const { data, error } = useApi<any>("/api/optimize/workloads");
  const [text, setText] = useState("");
  const [upErr, setUpErr] = useState<string | null>(null);
  const example = `[\n  {"id": "t1", "category": "classification", "task": "Classify the sentiment (positive, negative, neutral): \\"Fine, I guess.\\"",\n   "checks": [{"type": "label", "labels": ["positive", "negative", "neutral"], "answer": "neutral"}]}\n]`;
  function upload() {
    setUpErr(null);
    try {
      const parsed = JSON.parse(text);
      onCreate({ cases: parsed, title: "Uploaded workload" });
    } catch (e: any) {
      setUpErr(`Not valid JSON: ${e.message}`);
    }
  }
  return (
    <>
      <ErrorBox error={error} />
      {!data && !error && <Loading />}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {data?.workloads?.map((w: any) => {
          const cats = Array.from(new Set(w.cases.map((c: any) => c.category)));
          const checks = Array.from(new Set(w.cases.flatMap((c: any) => c.checks.map((k: any) => k.type))));
          return (
            <Card key={w.id} title={w.title} right={<Badge>{w.cases.length} tasks</Badge>}>
              <p className="text-sm">{w.description}</p>
              <p className="mt-2 text-xs text-muted">
                Categories: {cats.join(", ")}
                <br />
                Verified by: {checks.join(", ")}
              </p>
              <button className="btn mt-4" disabled={busy} onClick={() => onCreate({ preset: w.id })}>
                Select workload <Icon name="arrowRight" size={15} />
              </button>
            </Card>
          );
        })}
        {data && (
          <Card title="Upload your own" right={<Badge tone="info">JSON</Badge>}>
            <p className="text-sm">Up to 20 tasks. Each needs a deterministic check, so the gate can verify quality without trusting a model.</p>
            <textarea className="input mt-3 h-28 w-full font-mono text-xs" placeholder={example} value={text} onChange={(e) => setText(e.target.value)} aria-label="Workload JSON" />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <label className="btn cursor-pointer">
                Choose file
                <input
                  type="file"
                  accept=".json,application/json"
                  className="hidden"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (f) setText(await f.text());
                  }}
                />
              </label>
              <button className="btn btn-primary" disabled={busy || !text.trim()} onClick={upload}>
                Validate &amp; select
              </button>
            </div>
            {upErr && <p className="mt-2 text-xs text-bad">{upErr}</p>}
          </Card>
        )}
      </div>
      {data && (
        <p className="mt-3 text-xs text-muted">
          Baseline configuration: every task on <code>{data.baseline.model_id}</code> with no escalation. Analyst: <code>{data.analyst_model}</code>. Selecting a workload is free; nothing runs until you start the baseline.
        </p>
      )}
    </>
  );
}

function OptimizeInner() {
  const router = useRouter();
  const params = useSearchParams();
  const id = params.get("id");
  const [st, setSt] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [live, setLive] = useState<any[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number; run?: string } | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [rounds, setRounds] = useState(2);
  const [drill, setDrill] = useState(true);
  const [note, setNote] = useState("");
  const { data: history, reload: reloadHistory } = useApi<any>("/api/optimize/sessions?limit=10");

  const load = useCallback(async () => {
    if (!id) {
      setSt(null);
      return;
    }
    try {
      setSt(await apiGet(`/api/optimize/sessions/${id}`));
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (st?.analysis?.proposals && st.status === "proposed") setPicked(st.analysis.proposals.filter((p: any) => p.valid).map((p: any) => p.id));
  }, [st?.analysis, st?.status]);

  async function create(body: any) {
    setBusy("create");
    setErr(null);
    try {
      const s = await apiPost("/api/optimize/sessions", body);
      router.push(`/optimize?id=${s.id}`);
      reloadHistory();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function phase(name: "baseline" | "analyze" | "verify", body?: any) {
    if (!id) return;
    setBusy(name);
    setErr(null);
    setLive([]);
    setProgress(null);
    try {
      const s = await streamOptimize(id, name, body, (e) => {
        if (e.step === "task") setProgress({ done: e.data.done, total: e.data.total, run: e.run });
        else setLive((l) => [...l, e]);
      });
      setSt(s);
      reloadHistory();
    } catch (e: any) {
      setErr(e.message);
      load();
    } finally {
      setBusy(null);
      setProgress(null);
    }
  }

  async function decide(decision: "accept" | "reject") {
    if (!id) return;
    setBusy("decide");
    try {
      setSt(await apiPost(`/api/optimize/sessions/${id}/decision`, { decision, note }));
      reloadHistory();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  }

  const step = st ? stepOf(st) : 1;
  const best = useMemo(() => (st?.rounds || []).slice().reverse().find((r: any) => r.gate.accepted) || (st?.rounds || []).slice(-1)[0], [st]);
  const base = st?.baseline;
  const accessHint = err?.includes("access code") ? <span>Enter it in <Link className="underline" href="/settings">Settings</Link>.</span> : undefined;

  return (
    <div>
      <PageHeader
        title="Optimize a workload"
        subtitle="EcoCompute treats wasted inference compute as a fixable engineering problem. It measures your workload, has NVIDIA Nemotron diagnose the waste and propose bounded changes, then keeps only the changes that independent validators and measurements confirm. Nothing is applied without your approval."
        actions={st && <Link href="/optimize" className="btn">New session</Link>}
      />
      <SampleBanner show={st ? st.sample_data : history?.sample_data} />
      <ErrorBox error={err} hint={accessHint} />
      <Stepper current={step} done={step} />

      {!id && <WorkloadPicker onCreate={create} busy={!!busy} />}
      {id && !st && !err && <Loading />}

      {st && (
        <div className="space-y-4">
          <Card title={st.workload.title} subtitle={`${st.workload.cases.length} tasks · ${st.categories.join(", ")} · ${st.workload.source}`} right={<Badge tone={st.status === "accepted" ? "good" : st.status === "rejected" || st.status === "declined" ? "bad" : "info"}>{st.status.replaceAll("_", " ")}</Badge>}>
            <details className="text-xs">
              <summary className="cursor-pointer text-muted">Show tasks and their checks</summary>
              <ul className="mt-2 space-y-2">
                {st.workload.cases.map((c: any) => (
                  <li key={c.id} className="rounded-lg bg-panel-2 p-2">
                    <b>{c.id}</b> <span className="text-muted">({c.category})</span> — {c.task.slice(0, 180)}
                    {c.task.length > 180 && "…"}
                    <div className="text-muted">check: {c.checks.map((k: any) => k.type).join(", ")}</div>
                  </li>
                ))}
              </ul>
            </details>
          </Card>

          {/* 2. Baseline */}
          <Card title="2 · Baseline performance" subtitle="The workload as it runs today: every task on the largest model, no escalation.">
            {!base ? (
              <div className="flex flex-wrap items-center gap-3">
                <button className="btn btn-primary" disabled={!!busy} onClick={() => phase("baseline")}>
                  {busy === "baseline" ? "Measuring…" : "Run baseline"}
                </button>
                <span className="text-xs text-muted">Makes {st.workload.cases.length} real model calls. Requires the access code on the hosted demo.</span>
              </div>
            ) : (
              <>
                <Totals t={base.totals} e={base.energy_estimate} />
                <p className="mt-2 text-xs text-muted">
                  Measured {when(base.measured_at)} on <code>{base.provider}</code>. GPU utilisation and memory: not observable through a serverless API. Energy is a FLOPs-based estimate, not a power reading.
                </p>
              </>
            )}
          </Card>

          {/* 3 + 4. Analysis and review */}
          {base && (
            <Card title="3 · Nemotron analysis" subtitle="The analyst reads only measured numbers and may only propose three kinds of change. Everything it returns is validated before anything runs." right={st.analysis?.call && <code className="text-xs text-muted">{st.analysis.call.model}</code>}>
              {!st.analysis || st.status === "analysis_failed" ? (
                <>
                  {st.analysis?.error && <p className="mb-3 text-sm text-bad">Analyst output was rejected: {st.analysis.error}</p>}
                  <button className="btn btn-primary" disabled={!!busy} onClick={() => phase("analyze")}>
                    {busy === "analyze" ? "Nemotron is analysing…" : st.analysis ? "Retry analysis" : "Run Nemotron analysis"}
                  </button>
                </>
              ) : (
                <>
                  <ul className="space-y-2">
                    {st.analysis.diagnosis.map((d: any, i: number) => (
                      <li key={i} className="rounded-xl bg-panel-2 p-3 text-sm">
                        <div className="font-medium">{d.finding}</div>
                        <div className="text-xs text-muted">Evidence: {d.evidence}</div>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-muted">
                    Request <code>{st.analysis.call.request_id || "—"}</code> · {num(st.analysis.call.prompt_tokens)} in / {num(st.analysis.call.completion_tokens)} out tokens · {ms(st.analysis.call.latency_ms)} · {usd(st.analysis.call.cost_usd)} ·{" "}
                    {st.analysis.call.structured_output ? "JSON mode" : "plain JSON prompt (JSON mode unsupported)"}
                  </p>
                </>
              )}
            </Card>
          )}

          {st.analysis?.proposals?.length > 0 && (
            <Card title="4 · Review proposed changes" subtitle="Choose which proposals may be tested. Testing spends real calls; the live router is never changed by a test.">
              <ul className="space-y-2">
                {st.analysis.proposals.map((p: any) => (
                  <li key={p.id} className={`rounded-xl border p-3 ${p.valid ? "border-border" : "border-bad/30 bg-bad-soft"}`}>
                    <label className="flex gap-3">
                      <input
                        type="checkbox"
                        className="mt-1"
                        disabled={!p.valid || st.status !== "proposed" || !!busy}
                        checked={picked.includes(p.id)}
                        onChange={(e) => setPicked((x) => (e.target.checked ? [...x, p.id] : x.filter((y) => y !== p.id)))}
                      />
                      <span className="min-w-0 text-sm">
                        <span className="font-medium">{describe(p)}</span> <code className="text-xs text-muted">{p.id}</code>
                        {!p.valid && (
                          <span className="ml-2">
                            <Badge tone="bad">refused before execution</Badge>
                          </span>
                        )}
                        {p.rationale && <span className="block text-muted">{p.rationale}</span>}
                        {p.evidence && <span className="block text-xs text-muted">Evidence: {p.evidence}</span>}
                        {(p.expected_effect || p.risk) && (
                          <span className="block text-xs text-muted">
                            Expected: {p.expected_effect || "—"} · Risk: {p.risk || "—"}
                          </span>
                        )}
                        {!p.valid && <span className="block text-xs text-bad">{p.rejection}</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              {st.status === "proposed" && (
                <div className="mt-4 flex flex-wrap items-center gap-4">
                  <label className="text-sm">
                    Refinement rounds{" "}
                    <select className="input ml-1" value={rounds} onChange={(e) => setRounds(Number(e.target.value))}>
                      {[1, 2, 3].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={drill} onChange={(e) => setDrill(e.target.checked)} /> Include safety drill (injected bad proposals)
                  </label>
                  <button className="btn btn-primary" disabled={!!busy || !picked.length} onClick={() => phase("verify", { proposal_ids: picked, max_rounds: rounds, safety_drill: drill })}>
                    {busy === "verify" ? "Verifying…" : `Approve test of ${picked.length} proposal${picked.length === 1 ? "" : "s"}`}
                  </button>
                </div>
              )}
            </Card>
          )}

          {/* live progress for any phase */}
          {busy && busy !== "create" && busy !== "decide" && (
            <Card title={busy === "verify" ? "5 · Bounded verification (live)" : busy === "baseline" ? "Measuring baseline (live)" : "Analysis (live)"}>
              {progress && (
                <div className="mb-3">
                  <div className="mb-1 text-xs text-muted">
                    {progress.run}: {progress.done}/{progress.total} tasks
                  </div>
                  <div className="h-2 rounded-full bg-panel-2">
                    <div className="h-2 rounded-full bg-accent transition-all" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
                  </div>
                </div>
              )}
              <ul className="space-y-1 text-sm">
                {live.map((e, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="w-4 shrink-0 text-center" style={{ color: e.status === "failed" ? "var(--bad)" : e.status === "running" ? "var(--info)" : "var(--accent)" }}>
                      {e.status === "failed" ? "✕" : e.status === "running" ? "…" : "✓"}
                    </span>
                    <span>
                      {e.title}
                      {e.detail && <span className="block text-xs text-muted">{e.detail}</span>}
                    </span>
                  </li>
                ))}
                {!live.length && <li className="text-muted">Starting…</li>}
              </ul>
            </Card>
          )}

          {/* 5 + 6. Verification rounds and before/after */}
          {st.rounds?.length > 0 && !busy && (
            <>
              <Card title="5 · Verification gate" subtitle="Deterministic and independent of the model: no task that passed may fail, the pass count may not drop, and cost must fall.">
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  {st.rounds.map((r: any) => (
                    <div key={r.round} className="rounded-xl border border-border p-4">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <span className="font-medium">Round {r.round}</span>
                        <Badge tone={r.gate.accepted ? "good" : "bad"}>{r.gate.accepted ? "accepted" : "rejected"}</Badge>
                      </div>
                      <p className="mb-2 text-xs text-muted">{r.proposals.map(describe).join(" · ")}</p>
                      <GateChecks gate={r.gate} />
                      {r.refinement && <p className="mt-2 text-xs text-muted">Regressions were sent back to Nemotron, which revised its proposals for the next round.</p>}
                    </div>
                  ))}
                  {st.drill && (
                    <div className="rounded-xl border border-warn/40 p-4">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <span className="font-medium">Safety drill</span>
                        <Badge tone="warn">INJECTED</Badge>
                      </div>
                      <p className="mb-2 text-xs text-muted">Deliberately bad proposals inserted by EcoCompute, not by Nemotron, to prove the safeguards work.</p>
                      <ul className="mb-2 space-y-1 text-sm">
                        {st.drill.proposals.map((p: any) => (
                          <li key={p.id}>
                            {p.valid ? "Allowed by schema, tested: " : "Refused before execution: "}
                            <code className="text-xs">{p.type === "execute_command" ? p.requested?.command : describe(p)}</code>
                          </li>
                        ))}
                      </ul>
                      {st.drill.gate && <GateChecks gate={st.drill.gate} />}
                    </div>
                  )}
                </div>
              </Card>

              {best && (
                <Card title="6 · Before and after" subtitle={`Round ${best.round} vs baseline, same ${base.totals.tasks} tasks, temperature 0, one run each (n=${base.totals.tasks}).`} right={<Badge tone={best.gate.accepted ? "good" : "bad"}>{best.gate.accepted ? "verified" : "not verified"}</Badge>}>
                  <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
                    <Pair label="Tasks passed" base={base.totals.passed} cand={best.run.totals.passed} fmt={(v) => `${v}/${base.totals.tasks}`} lowerIsBetter={false} />
                    <Pair label="Inference cost" base={base.totals.cost_usd} cand={best.run.totals.cost_usd} fmt={(v) => usd(v)} />
                    <Pair label="Total tokens" base={base.totals.total_tokens} cand={best.run.totals.total_tokens} fmt={(v) => num(v)} />
                    <Pair label="Model time" base={base.totals.model_latency_ms} cand={best.run.totals.model_latency_ms} fmt={(v) => ms(v)} />
                    <Pair label="Model calls" base={base.totals.calls} cand={best.run.totals.calls} fmt={(v) => num(v)} />
                    <Pair label="Energy (estimate)" base={base.energy_estimate?.scenarios?.central?.energy_wh} cand={best.run.energy_estimate?.scenarios?.central?.energy_wh} fmt={(v) => sci(v, "Wh")} />
                  </div>
                  {st.recommendation && (
                    <p className="mt-4 rounded-xl bg-panel-2 p-3 text-sm">
                      One-time analysis cost {usd(st.recommendation.analysis_cost_usd)}.{" "}
                      {st.recommendation.break_even_runs != null
                        ? st.recommendation.break_even_runs <= 1
                          ? "Including the verification runs, the per-run saving repays the whole optimisation within the first production run of this workload."
                          : `Including the verification runs, the optimisation pays for itself after about ${Math.ceil(st.recommendation.break_even_runs)} runs of this workload.`
                        : "Break-even could not be computed (cost not available)."}
                    </p>
                  )}
                  <div className="mt-4">
                    <RunTable base={base} cand={best.run} />
                  </div>
                </Card>
              )}
            </>
          )}

          {base && !st.rounds?.length && !busy && (
            <Card title="Baseline tasks">
              <RunTable base={base} />
            </Card>
          )}

          {/* 7. Decision */}
          {["awaiting_approval", "rejected", "accepted", "declined"].includes(st.status) && !busy && (
            <Card title="7 · Decision" subtitle={st.status === "rejected" ? "No candidate passed the gate, so the current configuration stays." : "A verified recommendation is never applied automatically."}>
              {st.status === "awaiting_approval" && (
                <div className="flex flex-wrap items-center gap-3">
                  <input className="input min-w-[220px] flex-1" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                  <button className="btn btn-primary" disabled={!!busy} onClick={() => decide("accept")}>
                    Accept recommendation
                  </button>
                  <button className="btn" disabled={!!busy} onClick={() => decide("reject")}>
                    Reject
                  </button>
                </div>
              )}
              {st.decision && (
                <p className="text-sm">
                  <Badge tone={st.decision.decision === "accept" ? "good" : "bad"}>{st.decision.decision === "accept" ? "accepted" : "rejected"}</Badge> by a human {when(st.decision.at)}
                  {st.decision.note && <span className="text-muted"> · “{st.decision.note}”</span>}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-3">
                <button className="btn" onClick={async () => download(`ecocompute-recommendation-${id}.json`, await apiGet(`/api/optimize/sessions/${id}/export`))}>
                  <Icon name="doc" size={16} /> Export recommendation
                </button>
                <button className="btn" onClick={async () => download(`optimization-${id}-${st.provider}.json`, await apiGet(`/api/bundles/optimization/${id}`))}>
                  Export full evidence bundle
                </button>
              </div>
            </Card>
          )}

          {st.log?.length > 0 && (
            <Card title="Execution log" subtitle="Every phase, as recorded on the server.">
              <details>
                <summary className="cursor-pointer text-sm text-muted">{st.log.length} events</summary>
                <ol className="mt-2 space-y-1 text-xs">
                  {st.log.map((e: any, i: number) => (
                    <li key={i} className="grid grid-cols-[64px_70px_1fr] gap-2">
                      <span className="text-muted tabular-nums">{new Date(e.ts * 1000).toLocaleTimeString()}</span>
                      <span className="uppercase tracking-wide text-muted">{e.phase}</span>
                      <span>
                        <span style={{ color: e.status === "failed" ? "var(--bad)" : undefined }}>{e.title}</span>
                        {e.detail && <span className="block text-muted">{e.detail}</span>}
                      </span>
                    </li>
                  ))}
                </ol>
              </details>
            </Card>
          )}
        </div>
      )}

      <Card title="Previous sessions" className="mt-6">
        {!history ? (
          <Loading />
        ) : !history.items.length ? (
          <p className="text-sm text-muted">No optimization sessions yet. Pick a workload above to start one.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="data">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Workload</th>
                  <th>Status</th>
                  <th className="num">Tasks</th>
                  <th className="num">Rounds</th>
                  <th className="num">Δ cost</th>
                  <th>Drill</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((h: any) => (
                  <tr key={h.id}>
                    <td>
                      <Link className="underline" href={`/optimize?id=${h.id}`}>{when(h.created_at)}</Link> {h.provider !== "nebius" && <Badge tone="warn">{h.provider}</Badge>}
                    </td>
                    <td>{h.title}</td>
                    <td className="text-xs">{h.status.replaceAll("_", " ")}</td>
                    <td className="num">{h.summary.tasks}</td>
                    <td className="num">{h.summary.rounds}</td>
                    <td className="num">{signedPct(h.summary.cost_rel, 0)}</td>
                    <td className="text-xs">{h.summary.drill_rejected ? "rejected ✓" : "—"}</td>
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

export default function OptimizePage() {
  return (
    <Suspense fallback={<Loading />}>
      <OptimizeInner />
    </Suspense>
  );
}
