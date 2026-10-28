"use client";

import { useMemo } from "react";
import { useApi } from "@/lib/useApi";
import { ms, pct, usd } from "@/lib/format";
import { BackendHint, Card, ErrorBox, KV, Loading, PageHeader, SampleBanner, TierBadge } from "@/components/ui";

function cellBg(p: number) {
  // green intensity by posterior pass probability
  const a = Math.max(0, Math.min(1, (p - 0.4) / 0.6));
  return `color-mix(in srgb, var(--accent) ${Math.round(a * 45)}%, transparent)`;
}

export default function RouterPage() {
  const { data, error } = useApi<any>("/api/router/evidence");
  const { data: cfg } = useApi<any>("/api/config");
  const tiers: any[] = cfg?.tiers || [];
  const byCat = useMemo(() => {
    const m: Record<string, Record<string, any>> = {};
    for (const r of data?.evidence || []) (m[r.category] ||= {})[r.tier] = r;
    return m;
  }, [data]);

  return (
    <div>
      <PageHeader
        title="Router"
        subtitle="The routing policy keeps a Beta posterior over P(pass) for every (category, tier). A heuristic prior is updated with observed quality-gate outcomes, then the router picks the start tier whose whole escalation chain has the lowest expected cost while still meeting the quality target."
      />
      <ErrorBox error={error} hint={<BackendHint />} />
      <SampleBanner show={data?.sample_data} />
      {!data && !error && <Loading />}

      {cfg && (
        <div className="mb-4 grid gap-4 lg:grid-cols-2">
          <Card title="Model tiers">
            <table className="data">
              <thead>
                <tr>
                  <th>Tier</th>
                  <th>Model ID</th>
                  <th className="num">Active params</th>
                  <th className="num">$ / 1M in · out</th>
                </tr>
              </thead>
              <tbody>
                {tiers.map((t) => (
                  <tr key={t.key}>
                    <td>
                      <TierBadge tier={t.key} label={t.label} />
                    </td>
                    <td>
                      <code className="text-xs">{t.model_id}</code>
                    </td>
                    <td className="num">{t.active_params_b ? `${t.active_params_b}B` : "—"}</td>
                    <td className="num">
                      {t.price_in_per_m != null ? `$${t.price_in_per_m} · $${t.price_out_per_m}` : "not set"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Policy settings">
            <KV
              rows={[
                ["Baseline (for comparisons)", <TierBadge key="b" tier={cfg.baseline_tier} label={tiers.find((t) => t.key === cfg.baseline_tier)?.label} />],
                ["First-attempt pass floor", pct(cfg.min_start_pass, 0)],
                ["Exploration rate (playground)", pct(cfg.exploration_rate, 0)],
                ["Per-workload budget", usd(cfg.max_workload_cost_usd, 3)],
                ["Max output tokens", cfg.max_output_tokens],
                ["Temperature", cfg.temperature],
              ]}
            />
          </Card>
        </div>
      )}

      {data && (
        <Card title="Evidence: posterior P(pass) by category and tier">
          <div className="overflow-x-auto">
            <table className="data">
              <thead>
                <tr>
                  <th>Category</th>
                  {tiers.map((t) => (
                    <th key={t.key} className="num">
                      {t.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(byCat).map(([cat, row]) => (
                  <tr key={cat}>
                    <td>{cat}</td>
                    {tiers.map((t) => {
                      const r = row[t.key];
                      if (!r) return <td key={t.key} className="num">—</td>;
                      return (
                        <td key={t.key} className="num" style={{ background: cellBg(r.posterior_pass) }} title={`prior ${pct(r.prior_pass, 0)}; avg latency ${ms(r.avg_latency_ms)}; avg cost ${usd(r.avg_cost_usd, 6)}`}>
                          <div className="font-medium">{pct(r.posterior_pass, 0)}</div>
                          <div className="text-xs text-muted">
                            prior {pct(r.prior_pass, 0)} · {r.observed_passes}/{r.observed_n} observed
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted">
            Posterior = (k·prior + passes) / (k + n). Evidence comes only from objectively graded attempts recorded on the current provider; the warm benchmark condition uses calibration-split evidence only, so held-out test cases never inform their own routing.
          </p>
        </Card>
      )}
    </div>
  );
}
