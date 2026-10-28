"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { apiPost, streamWorkload, type TraceEvent } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ms, num, usd } from "@/lib/format";
import TraceView from "@/components/TraceView";
import { Badge, Card, ErrorBox, KV, PageHeader, SampleBanner, TierBadge, statusTone } from "@/components/ui";

const CATEGORIES = ["", "extraction", "summarization", "classification", "structured_json", "reasoning", "coding", "data_interpretation", "general"];

type Form = {
  task: string;
  category: string;
  output_format: "text" | "json" | "code";
  quality_threshold: number;
  allow_escalation: boolean;
  max_escalations: number;
  repair_attempts: number;
  forced_tier: string;
  use_judge: boolean;
  json_schema: string;
  required_terms: string;
  max_words: string;
  exact_answer: string;
};

const EMPTY: Form = {
  task: "",
  category: "",
  output_format: "text",
  quality_threshold: 0.8,
  allow_escalation: true,
  max_escalations: 2,
  repair_attempts: 0,
  forced_tier: "",
  use_judge: false,
  json_schema: "",
  required_terms: "",
  max_words: "",
  exact_answer: "",
};

function fromPreset(req: any): Form {
  return {
    ...EMPTY,
    task: req.task || "",
    category: req.category || "",
    output_format: req.output_format || "text",
    quality_threshold: req.quality_threshold ?? 0.8,
    allow_escalation: req.allow_escalation ?? true,
    max_escalations: req.max_escalations ?? 2,
    repair_attempts: req.repair_attempts ?? 0,
    forced_tier: req.forced_tier || "",
    use_judge: !!req.use_judge,
    json_schema: req.json_schema ? JSON.stringify(req.json_schema, null, 2) : "",
    required_terms: (req.required_terms || []).join("\n"),
    max_words: req.max_words ? String(req.max_words) : "",
    exact_answer: req.exact_answer || "",
  };
}

function toRequest(f: Form) {
  const body: any = {
    task: f.task,
    category: f.category || null,
    output_format: f.output_format,
    quality_threshold: f.quality_threshold,
    allow_escalation: f.allow_escalation,
    max_escalations: f.max_escalations,
    repair_attempts: f.repair_attempts,
    forced_tier: f.forced_tier || null,
    use_judge: f.use_judge,
    required_terms: f.required_terms.split("\n").map((s) => s.trim()).filter(Boolean),
    max_words: f.max_words ? Number(f.max_words) : null,
    exact_answer: f.exact_answer.trim() || null,
  };
  if (f.output_format === "json" && f.json_schema.trim()) {
    try {
      body.json_schema = JSON.parse(f.json_schema);
    } catch {
      throw new Error("JSON schema is not valid JSON.");
    }
  }
  return body;
}

export default function Playground() {
  const { data: presets } = useApi<any[]>("/api/presets");
  const { data: cfg } = useApi<any>("/api/config");
  const [form, setForm] = useState<Form>(EMPTY);
  const [presetId, setPresetId] = useState("");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [result, setResult] = useState<any>(null);
  const [preview, setPreview] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const tierLabel = (k?: string | null) => cfg?.tiers?.find((t: any) => t.key === k)?.label || k;
  const preset = presets?.find((p) => p.id === presetId);

  async function doPreview() {
    setError(null);
    try {
      const b = toRequest(form);
      setPreview(
        await apiPost("/api/router/preview", {
          task: b.task,
          category: b.category,
          output_format: b.output_format,
          quality_threshold: b.quality_threshold,
          allow_escalation: b.allow_escalation,
        }),
      );
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function run() {
    setError(null);
    setEvents([]);
    setResult(null);
    setRunning(true);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const done = await streamWorkload(toRequest(form), (e) => setEvents((xs) => [...xs, e]), ac.signal);
      setResult(done);
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Playground"
        subtitle="Run one workload through the router and watch every step live. Quality checks are deterministic: escalation happens only if the gate genuinely fails."
      />
      <SampleBanner show={cfg?.sample_data} />
      <ErrorBox
        error={error}
        hint={error?.includes("access code") ? <span>Enter it in <Link className="underline" href="/settings">Settings</Link>.</span> : undefined}
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Card title="Workload">
          <div className="space-y-3 text-sm">
            <label className="block">
              <span className="text-xs text-muted">Preset</span>
              <select
                className="input mt-1"
                value={presetId}
                onChange={(e) => {
                  setPresetId(e.target.value);
                  const p = presets?.find((x) => x.id === e.target.value);
                  setForm(p ? fromPreset(p.request) : EMPTY);
                  setPreview(null);
                }}
              >
                <option value="">Custom task</option>
                {presets?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
              {preset && <p className="mt-1 text-xs text-muted">{preset.blurb}</p>}
            </label>
            <label className="block">
              <span className="text-xs text-muted">Task</span>
              <textarea className="input mt-1 font-mono text-xs" rows={9} value={form.task} onChange={(e) => set("task", e.target.value)} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className="text-xs text-muted">Category</span>
                <select className="input mt-1" value={form.category} onChange={(e) => set("category", e.target.value)}>
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c || "auto-detect"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="text-xs text-muted">Output format</span>
                <select className="input mt-1" value={form.output_format} onChange={(e) => set("output_format", e.target.value as Form["output_format"])}>
                  <option value="text">text</option>
                  <option value="json">json</option>
                  <option value="code">code</option>
                </select>
              </label>
              <label>
                <span className="text-xs text-muted">Quality target: {Math.round(form.quality_threshold * 100)}%</span>
                <input
                  type="range"
                  min={0.5}
                  max={0.99}
                  step={0.01}
                  className="mt-2 w-full accent-[var(--accent)]"
                  value={form.quality_threshold}
                  onChange={(e) => set("quality_threshold", Number(e.target.value))}
                />
              </label>
              <label>
                <span className="text-xs text-muted">Start tier</span>
                <select className="input mt-1" value={form.forced_tier} onChange={(e) => set("forced_tier", e.target.value)}>
                  <option value="">router decides</option>
                  {cfg?.tiers?.map((t: any) => (
                    <option key={t.key} value={t.key}>
                      force {t.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.allow_escalation} onChange={(e) => set("allow_escalation", e.target.checked)} />
                Allow escalation
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.repair_attempts > 0} onChange={(e) => set("repair_attempts", e.target.checked ? 1 : 0)} />
                One repair attempt
              </label>
              <label className="flex items-center gap-2" title="Only used when there are no deterministic checks. Scored as an estimate.">
                <input type="checkbox" checked={form.use_judge} onChange={(e) => set("use_judge", e.target.checked)} />
                Model judge (estimate)
              </label>
            </div>

            <details className="rounded-lg border border-border p-3" open={!!(form.json_schema || form.required_terms || form.max_words || form.exact_answer)}>
              <summary className="cursor-pointer text-xs font-medium">Quality gate checks</summary>
              <div className="mt-3 space-y-3">
                {form.output_format === "json" && (
                  <label className="block">
                    <span className="text-xs text-muted">JSON schema</span>
                    <textarea className="input mt-1 font-mono text-xs" rows={6} value={form.json_schema} onChange={(e) => set("json_schema", e.target.value)} />
                  </label>
                )}
                <label className="block">
                  <span className="text-xs text-muted">Required terms (one per line)</span>
                  <textarea className="input mt-1 font-mono text-xs" rows={2} value={form.required_terms} onChange={(e) => set("required_terms", e.target.value)} />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label>
                    <span className="text-xs text-muted">Max words</span>
                    <input className="input mt-1" inputMode="numeric" value={form.max_words} onChange={(e) => set("max_words", e.target.value.replace(/\D/g, ""))} />
                  </label>
                  <label>
                    <span className="text-xs text-muted">Exact answer</span>
                    <input className="input mt-1" value={form.exact_answer} onChange={(e) => set("exact_answer", e.target.value)} />
                  </label>
                </div>
              </div>
            </details>

            <div className="flex gap-2">
              <button className="btn btn-primary" disabled={running || form.task.trim().length < 3} onClick={run}>
                {running ? "Running…" : "Run workload"}
              </button>
              <button className="btn" disabled={running || form.task.trim().length < 3} onClick={doPreview} title="Plan only, no model call">
                Preview routing (free)
              </button>
              {running && (
                <button className="btn" onClick={() => abortRef.current?.abort()}>
                  Stop watching
                </button>
              )}
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          {preview && !running && events.length === 0 && (
            <Card title="Routing preview (no model called)">
              <p className="mb-3 text-sm">{preview.decision.rationale}</p>
              <table className="data">
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th className="num">P(success)</th>
                    <th className="num">Expected cost</th>
                    <th>Feasible</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.decision.options.map((o: any) => (
                    <tr key={o.start_tier}>
                      <td>{o.chain.map((t: string) => tierLabel(t)).join(" → ")}</td>
                      <td className="num">{(o.success_prob * 100).toFixed(1)}%</td>
                      <td className="num">{o.expected_cost_usd != null ? usd(o.expected_cost_usd, 6) : `${o.expected_cost.toFixed(2)} rel.`}</td>
                      <td>{o.feasible ? <Badge tone="good">yes</Badge> : <Badge tone="bad">{o.reasons.join(", ") || "no"}</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          <Card title="Live trace" right={running && <Badge tone="info">streaming</Badge>}>
            {events.length === 0 ? <p className="text-sm text-muted">Run a workload to see Analyze → Select → Execute → Evaluate → Repair/Escalate → Record → Learn.</p> : <TraceView events={events} live={running} />}
          </Card>

          {result && (
            <Card
              title="Result"
              right={
                <span className="flex items-center gap-2">
                  <Badge tone={statusTone(result.status)}>{result.status}</Badge>
                  <Link className="text-xs underline" href={`/history/${result.id}`}>
                    details
                  </Link>
                </span>
              }
            >
              <KV
                rows={[
                  ["Path", <span key="p">{result.initial_tier !== result.final_tier ? <><TierBadge tier={result.initial_tier} label={tierLabel(result.initial_tier)} /> → </> : null}<TierBadge tier={result.final_tier} label={tierLabel(result.final_tier)} /></span>],
                  ["Model", <code key="m">{result.final_model || "—"}</code>],
                  ["Calls / escalations", `${result.calls} / ${result.escalations}`],
                  ["Tokens", `${num(result.prompt_tokens)} in · ${num(result.completion_tokens)} out${result.reasoning_tokens ? ` (${num(result.reasoning_tokens)} reasoning)` : ""}`],
                  ["Latency", ms(result.latency_ms)],
                  ["Cost", result.cost_usd != null ? usd(result.cost_usd, 6) : "unavailable (price not configured)"],
                  ["Evaluated by", result.eval_method || "—"],
                ]}
              />
              <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-panel-2 p-3 text-xs">{result.final_output || "(empty)"}</pre>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
