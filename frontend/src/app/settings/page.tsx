"use client";

import { useEffect, useState } from "react";
import { accessCode, apiBase, apiGet, defaultApiBase, setAccessCode, setApiBase } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ms, pct, usd } from "@/lib/format";
import { Badge, BackendHint, Card, ErrorBox, KV, PageHeader, TierBadge } from "@/components/ui";

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
        eyebrow="Configuration" title="Settings" subtitle="Connection settings are stored in this browser only. Backend configuration is read-only here and set through environment variables." />
      <div className="space-y-4">
        <Card title="Connection">
          <div className="grid gap-3 md:grid-cols-2">
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
          <Card title="Backend configuration">
            <KV
              rows={[
                ["Provider", <span key="p">{cfg.provider} {cfg.sample_data ? <Badge tone="warn">sample data</Badge> : <Badge tone="good">live</Badge>}</span>],
                ["Base URL", <code key="b">{cfg.base_url}</code>],
                ["API key configured", cfg.api_key_configured ? "yes" : "no"],
                ["Tiers", <span key="t" className="flex flex-col gap-1">{cfg.tiers.map((t: any) => <span key={t.key}><TierBadge tier={t.key} label={t.label} /> <code className="text-xs">{t.model_id}</code></span>)}</span>],
                ["Judge model", <code key="j">{cfg.judge_model}</code>],
                ["Spend today", `${usd(cfg.spend_today_usd, 4)} of ${usd(cfg.daily_budget_usd, 2)} (${cfg.calls_today} calls)`],
                ["Per-workload budget", usd(cfg.max_workload_cost_usd, 3)],
                ["Benchmark call cap", cfg.benchmark_max_calls],
                ["Rate limit", `${cfg.rate_limit_per_minute} paid requests / min`],
                ["Code execution validator", cfg.code_execution_enabled ? "enabled (sandboxed)" : "disabled"],
                ["First-attempt pass floor", pct(cfg.min_start_pass, 0)],
              ]}
            />
          </Card>
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
