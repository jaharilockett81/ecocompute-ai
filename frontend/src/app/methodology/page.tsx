"use client";

import { useApi } from "@/lib/useApi";
import { Card, PageHeader } from "@/components/ui";

function Eq({ children }: { children: React.ReactNode }) {
  return <pre className="my-2 overflow-x-auto rounded-lg bg-panel-2 p-3 font-mono text-xs">{children}</pre>;
}

export default function Methodology() {
  const { data } = useApi<any>("/api/impact");
  const m = data?.methodology;

  return (
    <div className="max-w-4xl">
      <PageHeader title="Methodology" subtitle="How EcoCompute decides, how it checks quality, how the benchmark is run, and what the impact numbers do and do not mean." />
      <div className="space-y-4 text-sm leading-relaxed">
        <Card title="1 · Routing policy">
          <p>
            For each tier <i>i</i> the router holds p<sub>i</sub>, the probability that the tier&apos;s output passes the quality gate for the task&apos;s category, and c<sub>i</sub>, its expected cost per call. Starting at tier <i>s</i> and escalating on failure:
          </p>
          <Eq>{`E[cost | s] = Σ_{k=s..K} c_k · Π_{j=s..k-1} (1 − p_j)
P[pass | s] = 1 − Π_{k=s..K} (1 − p_k)`}</Eq>
          <p>
            It picks the cheapest start tier whose chain meets the quality target, whose own first-attempt pass probability is at least the floor (default 50%, since a cheap call that usually fails still wastes compute and doubles latency), and that fits the cost and latency limits. If none qualifies it starts at the most reliable tier.
          </p>
          <p className="mt-2">
            p<sub>i</sub> is a Beta posterior mean with pseudo-count k = 4: a documented heuristic prior per (category, tier), reduced for complex tasks, updated with the observed pass/fail counts. The prior is an assumption, not a trained model, and it fades as evidence accumulates. Expected tokens use observed averages once a (category, tier) has three or more graded attempts.
          </p>
        </Card>

        <Card title="2 · Quality gate">
          <p>Every benchmark task and every preset is graded deterministically. Validators include JSON Schema, exact field equality on dotted paths, exact / label / numeric (with tolerance) / regex answers, required terms, word and bullet limits, and Python unit tests executed in a sandboxed subprocess with a timeout.</p>
          <p className="mt-2">
            When a task has no deterministic check, the output is marked <b>unverified</b>. An optional model judge can score it, but the score is labelled an <i>estimate</i> and its cost is counted as overhead. Judge scores are never used in benchmark results.
          </p>
          <p className="mt-2">On failure the router may make one bounded repair attempt on the same tier (structural failures only, with the validator&apos;s message as feedback), then escalate to the next tier with a fresh prompt.</p>
        </Card>

        <Card title="3 · Benchmark design">
          <ul className="list-disc space-y-1 pl-5">
            <li>EcoBench v1: 49 original tasks in 7 categories (extraction, summarization, classification, structured JSON, reasoning, coding, data interpretation). 14 calibration and 35 held-out test cases.</li>
            <li>Conditions: <code>fixed:&lt;tier&gt;</code> always uses one model; <code>adaptive</code> routes from the prior only (cold); <code>adaptive_warm</code> routes with evidence from the calibration split only, so no test case informs its own routing.</li>
            <li>All conditions run the same cases at temperature 0, so comparisons are paired.</li>
            <li>Pass rates carry Wilson 95% intervals. Differences versus the baseline carry paired bootstrap 95% intervals over tasks.</li>
            <li>Cost is provider-reported tokens × configured price. Hidden reasoning tokens are included because they are billed as completion tokens.</li>
            <li>Results come only from stored records of real calls. Runs on the offline mock provider are labelled sample data everywhere and never reported.</li>
          </ul>
        </Card>

        <Card title="4 · Environmental impact estimate">
          {!m ? (
            <p className="text-muted">Loading parameters from the backend…</p>
          ) : (
            <>
              <Eq>{Object.entries(m.equations).map(([k, v]) => `${k.padEnd(22)} ${v}`).join("\n")}</Eq>
              <p>
                η<sub>peak</sub> = {(m.eta_peak_flop_per_joule / 1e12).toFixed(2)} TFLOP/J (H100 dense BF16 / 700 W). Active parameters per tier:{" "}
                {Object.entries(m.active_params_b).map(([t, p]: [string, any]) => `${t} ${p ?? "?"}B`).join(", ")}.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Scenario</th>
                      <th className="num">MFU prefill</th>
                      <th className="num">MFU decode</th>
                      <th className="num">System overhead</th>
                      <th className="num">Grid gCO₂e/kWh</th>
                      <th className="num">WUE L/kWh</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.scenarios.map((s: any) => (
                      <tr key={s.name}>
                        <td>{s.name}</td>
                        <td className="num">{s.mfu_prefill}</td>
                        <td className="num">{s.mfu_decode}</td>
                        <td className="num">{s.system_overhead}×</td>
                        <td className="num">{s.grid_g_per_kwh}</td>
                        <td className="num">{s.wue_l_per_kwh}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3 className="mt-4 font-semibold">Assumptions</h3>
              <ul className="list-disc space-y-1 pl-5">
                {m.assumptions.map((a: string) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
              <h3 className="mt-4 font-semibold">Not observable</h3>
              <ul className="list-disc space-y-1 pl-5">
                {m.not_observable.map((a: string) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
              <h3 className="mt-4 font-semibold">Sources</h3>
              <ul className="list-disc space-y-1 pl-5">
                {m.sources.map((s: any) => (
                  <li key={s.id}>
                    <a className="underline" href={s.url} target="_blank" rel="noreferrer">
                      {s.title}
                    </a>
                    : {s.used_for}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title="5 · Limitations">
          <ul className="list-disc space-y-1 pl-5">
            <li>35 held-out tasks give wide intervals; small differences are not claimed as significant.</li>
            <li>Category heuristics in the analyzer are keyword-based and can misclassify; callers can set the category explicitly.</li>
            <li>Prices and model IDs are configuration, verified against the authenticated Nebius catalog at startup and in Settings.</li>
            <li>Environmental figures are scenario estimates, not measurements, and are shown with their bounds.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
