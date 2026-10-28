"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/useApi";
import { ms, num, usd, when } from "@/lib/format";
import TraceView from "@/components/TraceView";
import { Badge, Card, ErrorBox, KV, Loading, PageHeader, SampleBanner, TierBadge, statusTone } from "@/components/ui";

export default function WorkloadDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: w, error } = useApi<any>(`/api/workloads/${id}`);

  return (
    <div>
      <PageHeader
        title="Workload"
        subtitle={w && `${when(w.created_at)} · ${w.source}${w.run_id ? ` · ${w.case_id} · ${w.condition}` : ""}`}
        actions={
          w?.run_id ? (
            <Link className="btn" href={`/benchmarks/${w.run_id}`}>
              Back to run
            </Link>
          ) : (
            <Link className="btn" href="/history">
              History
            </Link>
          )
        }
      />
      <ErrorBox error={error} />
      <SampleBanner show={w && w.provider !== "nebius"} />
      {!w && !error && <Loading />}
      {w && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <Card title="Summary" right={<Badge tone={statusTone(w.status)}>{w.status}</Badge>}>
              <KV
                rows={[
                  ["Category", w.category],
                  ["Path", <span key="p">{w.initial_tier !== w.final_tier && <><TierBadge tier={w.initial_tier} /> → </>}<TierBadge tier={w.final_tier} /></span>],
                  ["Final model", <code key="m">{w.final_model || "—"}</code>],
                  ["Calls / escalations", `${w.calls} / ${w.escalations}`],
                  ["Tokens", `${num(w.prompt_tokens)} in · ${num(w.completion_tokens)} out${w.reasoning_tokens ? ` (${num(w.reasoning_tokens)} reasoning)` : ""}`],
                  ["Latency", ms(w.latency_ms)],
                  ["Cost", `${usd(w.cost_usd, 6)}${w.overhead_cost_usd ? ` (judge overhead ${usd(w.overhead_cost_usd, 6)})` : ""}`],
                  ["Evaluated by", w.eval_method || "—"],
                  ["Provider", w.provider],
                ]}
              />
            </Card>
            <Card title="Task">
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs">{w.task_text}</pre>
            </Card>
            <Card title="Final output">
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-panel-2 p-3 text-xs">{w.final_output || "(empty)"}</pre>
            </Card>
          </div>
          <div className="space-y-4">
            <Card title="Trace">{w.trace?.length ? <TraceView events={w.trace} /> : <p className="text-sm text-muted">No trace recorded.</p>}</Card>
            {w.attempts?.length > 0 && (
              <Card title="Attempts">
                <div className="overflow-x-auto">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Role</th>
                        <th>Tier</th>
                        <th>Passed</th>
                        <th className="num">Tokens</th>
                        <th className="num">Latency</th>
                        <th className="num">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {w.attempts.map((a: any) => (
                        <tr key={a.id ?? `${a.idx}-${a.role}`}>
                          <td>{a.idx}</td>
                          <td>{a.role}</td>
                          <td>
                            <TierBadge tier={a.tier} />
                          </td>
                          <td>{a.passed === true ? <Badge tone="good">yes</Badge> : a.passed === false ? <Badge tone="bad">no</Badge> : <Badge>{a.ok ? "n/a" : "error"}</Badge>}</td>
                          <td className="num">
                            {num(a.prompt_tokens)} / {num(a.completion_tokens)}
                          </td>
                          <td className="num">{ms(a.latency_ms)}</td>
                          <td className="num">{usd(a.cost_usd, 6)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
