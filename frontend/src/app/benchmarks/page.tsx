"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { pct, when } from "@/lib/format";
import { Badge, BackendHint, Card, ErrorBox, PageHeader, SampleBanner, statusTone } from "@/components/ui";

const CONDITIONS = [
  { id: "fixed:small", hint: "always Nano" },
  { id: "fixed:medium", hint: "always Super" },
  { id: "fixed:large", hint: "always Ultra (baseline)" },
  { id: "adaptive", hint: "router, cold start" },
  { id: "adaptive_warm", hint: "router + calibration evidence" },
];

export default function BenchmarkLab() {
  const router = useRouter();
  const { data: runs, error, reload } = useApi<any>("/api/benchmarks", { poll: true, intervalMs: 5000 });
  const { data: ds } = useApi<any>("/api/benchmark/dataset");
  const { data: cfg } = useApi<any>("/api/config");
  const [conds, setConds] = useState<string[]>(["fixed:large", "adaptive", "adaptive_warm"]);
  const [split, setSplit] = useState("test");
  const [limit, setLimit] = useState("");
  const [repeats, setRepeats] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const cases = (ds?.cases || []).filter((c: any) => split === "all" || c.split === split);
  const n = limit ? Math.min(Number(limit), cases.length) : cases.length;
  const worst = n * repeats * conds.reduce((s, c) => s + (c.startsWith("fixed:") ? 1 : (cfg?.tiers?.length || 3)), 0);

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      const run = await apiPost("/api/benchmarks", { conditions: conds, split, limit: limit ? Number(limit) : null, repeats });
      reload();
      router.push(`/benchmarks/${run.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Benchmark Lab"
        subtitle={`EcoBench v1: ${ds?.cases?.length ?? "…"} original tasks across 7 categories, each with a deterministic check. Calibration cases warm the router; held-out test cases measure it. Every condition runs the same cases so results are paired.`}
      />
      <ErrorBox error={error || err} hint={error ? <BackendHint /> : undefined} />
      <SampleBanner show={runs?.sample_data} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Card title="Configure a run" subtitle="Same cases, same validators, temperature 0 for every condition.">
          <div className="space-y-3 text-sm">
            <div>
              <div className="mb-1 text-xs text-muted">Conditions (first fixed:large is the baseline)</div>
              {CONDITIONS.map((c) => (
                <label key={c.id} className="flex items-center gap-2 py-0.5">
                  <input
                    type="checkbox"
                    checked={conds.includes(c.id)}
                    onChange={(e) => setConds((xs) => (e.target.checked ? [...xs, c.id] : xs.filter((x) => x !== c.id)))}
                  />
                  <code>{c.id}</code> <span className="text-xs text-muted">{c.hint}</span>
                </label>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <label>
                <span className="text-xs text-muted">Split</span>
                <select className="input mt-1" value={split} onChange={(e) => setSplit(e.target.value)}>
                  <option value="test">test</option>
                  <option value="calib">calib</option>
                  <option value="all">all</option>
                </select>
              </label>
              <label>
                <span className="text-xs text-muted">Limit cases</span>
                <input className="input mt-1" placeholder="all" value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, ""))} />
              </label>
              <label>
                <span className="text-xs text-muted">Repeats</span>
                <select className="input mt-1" value={repeats} onChange={(e) => setRepeats(Number(e.target.value))}>
                  {[1, 2, 3].map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </label>
            </div>
            {split !== "test" && (
              <p className="rounded-xl bg-warn-soft p-2 text-xs text-warn">
                {split === "calib" ? "Calibration split: routing evidence only. Its results are not reported as held-out performance." : "All cases mixes calibration and held-out data; use the test split for reported results."}
              </p>
            )}
            <p className="text-xs text-muted">
              {n} cases × {conds.length} conditions × {repeats} repeat(s). Worst case {worst} calls (cap {cfg?.benchmark_max_calls ?? "…"}). Spend stops at the daily budget.
            </p>
            <button className="btn btn-primary" disabled={busy || conds.length === 0} onClick={start}>
              {busy ? "Starting…" : "Start benchmark"}
            </button>
          </div>
        </Card>

        <Card title="Runs">
          {!runs?.items?.length ? (
            <p className="text-sm text-muted">No runs yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="data">
                <thead>
                  <tr>
                    <th>Started</th>
                    <th>Conditions</th>
                    <th>Status</th>
                    <th className="num">Progress</th>
                    <th className="num">Best pass rate</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.items.map((r: any) => {
                    const rates = Object.values(r.summary?.conditions || {}).map((m: any) => m.success_rate ?? 0);
                    return (
                      <tr key={r.id}>
                        <td>
                          <Link className="underline" href={`/benchmarks/${r.id}`}>
                            {when(r.created_at)}
                          </Link>
                          {r.provider !== "nebius" && (
                            <span className="ml-1">
                              <Badge tone="warn">{r.provider}</Badge>
                            </span>
                          )}
                        </td>
                        <td className="text-xs">{(r.conditions || []).join(", ")}</td>
                        <td>
                          <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                        </td>
                        <td className="num">
                          <div className="ml-auto flex w-28 items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-panel-2" aria-hidden>
                              <div className="h-1.5 rounded-full bg-accent" style={{ width: `${r.progress_total ? (100 * r.progress_done) / r.progress_total : 0}%` }} />
                            </div>
                            <span className="text-xs">{r.progress_done}/{r.progress_total}</span>
                          </div>
                        </td>
                        <td className="num">{rates.length ? pct(Math.max(...rates)) : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
