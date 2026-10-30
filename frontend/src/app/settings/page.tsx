"use client";

import { useEffect, useState } from "react";
import { accessCode, apiBase, apiGet, defaultApiBase, setAccessCode, setApiBase } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ms, pct, usd } from "@/lib/format";
import { Badge, BackendHint, Card, ErrorBox, KV, PageHeader, TierBadge } from "@/components/ui";

function Check({ ok, label, detail, warnOnly }: { ok: boolean; label: string; detail: string; warnOnly?: boolean }) {
  const tone = ok ? "text-accent" : warnOnly ? "text-warn" : "text-bad";
  return (
    <li className="flex items-start gap-3 rounded-2xl border border-border p-3">
      <span aria-hidden className={`mt-0.5 text-base leading-none ${tone}`}>{ok ? "●" : "○"}</span>
      <span>
        <span className="font-medium">{label}</span>
        <span className="sr-only">: {ok ? "ok" : "attention"}</span>
        <span className="block text-xs text-muted">{detail}</span>
      </span>
    </li>
  );
}

function SpendMeter({ spent, budget, calls }: { spent: number; budget: number; calls: number }) {
  const frac = budget > 0 ? Math.min(1, spent / budget) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span>
          <span className="display text-2xl">{usd(spent, 4)}</span> <span className="text-muted">spent today of {usd(budget, 2)}</span>
        </span>
        <span className="text-xs text-muted">{calls} calls</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-panel-2" role="meter" aria-valuemin={0} aria-valuemax={budget} aria-valuenow={spent} aria-label="Daily spend">
        <div className={`h-2 rounded-full ${frac > 0.8 ? "bg-warn" : "bg-accent"}`} style={{ width: `${Math.max(frac * 100, spent > 0 ? 1 : 0)}%` }} />
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { data: cfg, error, reload } = useApi<any>("/api/config");
  const [base, setBase] = useState("");
  const [code, setCode] = useState("");
  const [saved, setSaved] = useState(false);
  const [diag, setDiag] = useState<any>(null);
  const [diagErr, setDiagErr] = useState<string | null>(null);
  const [diagBusy, setDiagBusy] = useState(false);

  useEffect(() => {
    setBase(apiBase());
    setCode(accessCode() || "");
  }, []);

  function save() {
    setApiBase(base.trim() && base.trim() !== defaultApiBase() ? base.trim() : null);
    setAccessCode(code.trim() || null);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    reload();
  }

  async function runDiag(ping: boolean) {
    setDiagBusy(true);
    setDiagErr(null);
    try {
      setDiag(await apiGet(`/api/diagnostics/provider${ping ? "?ping=true" : ""}`));
    } catch (e: any) {
      setDiagErr(e.message);
    } finally {
      setDiagBusy(false);
    }
  }

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="Settings" subtitle="Connection settings are stored in this browser only. Backend configuration is read-only here and set through environment variables." />
      <div className="space-y-4">
        <Card title="Connection">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="text-sm">
              <span className="text-xs text-muted">Backend API URL</span>
              <input className="input mt-1" value={base} onChange={(e) => setBase(e.target.value)} placeholder={defaultApiBase()} />
            </label>
            <label className="text-sm">
              <span className="text-xs text-muted">Demo access code {cfg?.access_code_required ? <Badge tone="warn">required for paid calls</Badge> : <Badge>not required</Badge>}</span>
              <input className="input mt-1" type="password" value={code} onChange={(e) => setCode(e.target.value)} placeholder="from the submission's testing instructions" />
            </label>
          </div>
          <button className="btn btn-primary mt-3" onClick={save}>
            {saved ? "Saved" : "Save"}
          </button>
        </Card>

        <ErrorBox error={error} hint={<BackendHint />} />

        {cfg && (
          <>
            <Card title="Secure configuration" subtitle="Secrets stay on the backend. The browser only learns whether they are set.">
              <ul className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                <Check ok={cfg.api_key_configured} label="Nebius API key" detail={cfg.api_key_configured ? "set on the backend, never sent to the browser" : "not set: offline mock provider, sample data only"} />
                <Check ok={!cfg.sample_data} label="Real inference" detail={cfg.sample_data ? "mock provider; numbers are placeholders" : `${cfg.provider} at ${cfg.base_url}`} />
                <Check ok={cfg.access_code_required} warnOnly label="Demo access code" detail={cfg.access_code_required ? "required for paid calls" : "not required (fine locally; set one before sharing a public URL)"} />
                <Check ok={cfg.code_execution_enabled} warnOnly label="Code validator" detail={cfg.code_execution_enabled ? "sandboxed subprocess with a timeout" : "disabled; coding tasks are unverified"} />
              </ul>
            </Card>

            <Card title="Cost controls" subtitle="Hard limits enforced by the backend before every paid call.">
              <SpendMeter spent={cfg.spend_today_usd} budget={cfg.daily_budget_usd} calls={cfg.calls_today} />
              <div className="mt-4">
                <KV
                  rows={[
                    ["Per-workload budget", usd(cfg.max_workload_cost_usd, 3)],
                    ["Benchmark call cap", cfg.benchmark_max_calls],
                    ["Rate limit", `${cfg.rate_limit_per_minute} paid requests / min`],
                    ["Max output tokens", cfg.max_output_tokens],
                    ["First-attempt pass floor", pct(cfg.min_start_pass, 0)],
                  ]}
                />
              </div>
            </Card>

            <Card title="Models" subtitle="Configured by environment variables; verify them against the catalog below.">
              <KV
                rows={[
                  ["Tiers", <span key="t" className="flex flex-col gap-1">{cfg.tiers.map((t: any) => <span key={t.key}><TierBadge tier={t.key} label={t.label} /> <code className="text-xs">{t.model_id}</code></span>)}</span>],
                  ["Optimizer analyst", <code key="a">{cfg.analyst_model}</code>],
                  ["Judge model (estimates only)", <code key="j">{cfg.judge_model}</code>],
                  ["Baseline tier", <TierBadge key="b" tier={cfg.baseline_tier} />],
                  ["Temperature", cfg.temperature],
                ]}
              />
            </Card>
          </>
        )}

        <Card title="Provider diagnostics" right={<span className="flex gap-2"><button className="btn" disabled={diagBusy} onClick={() => runDiag(false)}>Check catalog</button><button className="btn" disabled={diagBusy} onClick={() => runDiag(true)} title="Makes one tiny paid call to the smallest tier">Catalog + ping</button></span>}>
          <ErrorBox error={diagErr} />
          {!diag && !diagErr && <p className="text-sm text-muted">Checks that each configured model ID exists in the authenticated Nebius catalog.</p>}
          {diag && (
            <div className="space-y-3 text-sm">
              {diag.catalog_error && <div className="text-bad">{diag.catalog_error}</div>}
              {diag.tiers && (
                <table className="data">
                  <tbody>
                    {diag.tiers.map((t: any) => (
                      <tr key={t.tier}>
                        <td><TierBadge tier={t.tier} /></td>
                        <td><code className="text-xs">{t.model_id}</code></td>
                        <td>{t.in_catalog ? <Badge tone="good">in catalog</Badge> : <Badge tone="bad">missing</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {diag.nvidia_models_in_catalog?.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-xs text-muted">NVIDIA models in catalog ({diag.nvidia_models_in_catalog.length})</summary>
                  <ul className="mt-1 font-mono text-xs">{diag.nvidia_models_in_catalog.map((m: string) => <li key={m}>{m}</li>)}</ul>
                </details>
              )}
              {diag.ping && (
                <KV
                  rows={[
                    ["Ping", diag.ping.ok ? <Badge key="ok" tone="good">ok</Badge> : <Badge key="no" tone="bad">{diag.ping.error || "failed"}</Badge>],
                    ["Model reported", <code key="m">{diag.ping.model}</code>],
                    ["Reply", diag.ping.content],
                    ["Tokens", `${diag.ping.prompt_tokens} in / ${diag.ping.completion_tokens} out`],
                    ["Latency", ms(diag.ping.latency_ms)],
                    ["Request id", <code key="r">{diag.ping.request_id || "—"}</code>],
                  ]}
                />
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
