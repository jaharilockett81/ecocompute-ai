"use client";

import { useState } from "react";
import type { TraceEvent } from "@/lib/api";
import { ms, num, pct, usd } from "@/lib/format";
import { Badge, TierBadge, statusTone } from "./ui";

const STEP_LABEL: Record<string, string> = {
  start: "Start",
  analyze: "Analyze",
  select: "Select",
  infer: "Execute",
  inject: "Inject",
  evaluate: "Evaluate",
  approve: "Approve",
  repair: "Repair",
  escalate: "Escalate",
  guardrail: "Guardrail",
  record: "Record",
  learn: "Learn",
  final: "Result",
};

function dotColor(status: string, step?: string) {
  if (step === "inject") return "var(--warn)";
  return status === "done" ? "var(--accent)" : status === "failed" ? "var(--bad)" : status === "running" ? "var(--info)" : "var(--muted)";
}

/** Hide an "infer running" event once its matching done/failed event has arrived. */
function collapse(events: TraceEvent[]): TraceEvent[] {
  return events.filter((e, i) => !(e.step === "infer" && e.status === "running" && events.slice(i + 1).some((n) => n.step === "infer" && n.status !== "running")));
}

function Detail({ e }: { e: TraceEvent }) {
  const d = e.data || {};
  if (e.step === "analyze") {
    return (
      <div className="space-y-1 text-xs text-muted">
        <div>
          category <b className="text-fg">{d.category}</b> ({d.category_source}) · complexity <b className="text-fg">{d.complexity?.toFixed?.(2)}</b> ·
          ~{d.input_tokens_est} input tokens · expects ~{d.expected_output_tokens} output tokens
        </div>
        {d.signals?.length > 0 && <div>signals: {d.signals.join(" · ")}</div>}
      </div>
    );
  }
  if (e.step === "select" && d.estimates) {
    return (
      <div className="overflow-x-auto">
        <table className="data mt-1">
          <thead>
            <tr>
              <th>Tier</th>
              <th className="num">Prior P(pass)</th>
              <th className="num">Evidence</th>
              <th className="num">Posterior</th>
              <th className="num">Est. cost</th>
            </tr>
          </thead>
          <tbody>
            {d.estimates.map((t: any) => (
              <tr key={t.tier}>
                <td>
                  <TierBadge tier={t.tier} label={t.label} />
                </td>
                <td className="num">{pct(t.prior_pass, 0)}</td>
                <td className="num">
                  {t.observed_passes}/{t.observed_n}
                </td>
                <td className="num">{pct(t.pass_prob, 0)}</td>
                <td className="num">{t.est_cost_usd != null ? usd(t.est_cost_usd, 6) : `${t.cost_proxy?.toFixed?.(2)} rel.`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-1 text-xs text-muted">
          chain: {d.chain?.join(" → ")} {d.forced && <Badge tone="warn">forced start</Badge>} {d.explored && <Badge tone="info">exploration</Badge>}
        </div>
      </div>
    );
  }
  if (e.step === "infer" && e.status !== "running") {
    return (
      <div className="text-xs text-muted">
        <code className="text-fg">{d.model}</code> · {num(d.prompt_tokens)} in / {num(d.completion_tokens)} out
        {d.reasoning_tokens ? ` (${num(d.reasoning_tokens)} reasoning)` : ""} · {ms(d.latency_ms)} · {usd(d.cost_usd, 6)}
        {d.finish_reason && d.finish_reason !== "stop" && (
          <>
            {" "}
            · <Badge tone="warn">finish: {d.finish_reason}</Badge>
          </>
        )}
        {d.retries > 0 && ` · ${d.retries} retr${d.retries === 1 ? "y" : "ies"}`}
        {d.provider && d.provider !== "nebius" && (
          <>
            {" "}
            · <Badge tone="warn">provider: {d.provider}</Badge>
          </>
        )}
        {d.error && <div className="text-bad">{d.error}</div>}
      </div>
    );
  }
  if (e.step === "inject") {
    return (
      <div className="text-xs">
        <Badge tone="warn">INJECTED · not a model failure</Badge>
        {d.mutation === "field_value" ? (
          <span className="ml-2 text-muted">
            <code className="text-fg">{d.path}</code> set to <code className="text-fg">{JSON.stringify(d.injected_value)}</code> (correct: <code className="text-fg">{JSON.stringify(d.expected)}</code>)
          </span>
        ) : (
          <span className="ml-2 text-muted">answer replaced with a marker</span>
        )}
      </div>
    );
  }
  if (e.step === "evaluate" && d.method) {
    return (
      <div className="text-xs text-muted">
        method <code className="text-fg">{d.method}</code>
        {d.score != null && ` · score ${pct(d.score, 0)}`}
        {d.failures?.length > 0 && !e.detail && <div className="mt-0.5 text-bad">{d.failures.slice(0, 5).join(" · ")}</div>}
      </div>
    );
  }
  if (e.step === "record") {
    return (
      <div className="text-xs text-muted">
        {d.calls} call(s) · {num(d.prompt_tokens)} in / {num(d.completion_tokens)} out · {ms(d.latency_ms)} ·{" "}
        {d.cost_complete ? usd(d.cost_usd, 6) : "cost unavailable"}
        {d.overhead_cost_usd > 0 && ` (incl. ${usd(d.overhead_cost_usd, 6)} judge overhead)`}
      </div>
    );
  }
  if (e.step === "learn" && d.tiers?.length) {
    return (
      <div className="text-xs text-muted">
        {d.tiers.map((t: any) => `${t.tier}: ${t.passes}/${t.n} → ${pct(t.posterior, 0)}`).join(" · ")}
      </div>
    );
  }
  return null;
}

export default function TraceView({ events, live }: { events: TraceEvent[]; live?: boolean }) {
  const [raw, setRaw] = useState(false);
  const shown = collapse(events);
  return (
    <div>
      <ol className="relative ml-2 border-l border-border">
        {shown.map((e) => (
          <li key={e.seq} className="mb-3 ml-4">
            <span
              className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ${e.status === "running" && live ? "animate-pulse" : ""}`}
              style={{ background: dotColor(e.status, e.step) }}
            />
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="w-16 shrink-0 text-xs uppercase tracking-wide text-muted">{STEP_LABEL[e.step] || e.step}</span>
              <span className="text-sm font-medium">{e.title}</span>
              {e.status === "failed" && <Badge tone={statusTone("failed")}>failed</Badge>}
            </div>
            {e.detail && !["infer", "record"].includes(e.step) && <div className="ml-[72px] text-xs text-muted">{e.detail}</div>}
            <div className="ml-[72px]">
              <Detail e={e} />
            </div>
          </li>
        ))}
      </ol>
      {events.length > 0 && (
        <div>
          <button className="text-xs text-muted underline" onClick={() => setRaw(!raw)}>
            {raw ? "Hide" : "Show"} machine-readable trace
          </button>
          {raw && <pre className="mt-2 max-h-96 overflow-auto rounded-xl bg-panel-2 p-3 text-xs">{JSON.stringify(events, null, 2)}</pre>}
        </div>
      )}
    </div>
  );
}
