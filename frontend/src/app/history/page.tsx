"use client";

import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/useApi";
import { ms, num, usd, when } from "@/lib/format";
import { Badge, BackendHint, Card, ErrorBox, Loading, PageHeader, SampleBanner, statusTone, TierBadge } from "@/components/ui";

const PAGE = 50;

export default function HistoryPage() {
  const [source, setSource] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error } = useApi<any>(`/api/workloads?limit=${PAGE}&offset=${offset}${source ? `&source=${source}` : ""}`);
  const items: any[] = data?.items || [];

  return (
    <div>
      <PageHeader
        title="History"
        subtitle="Every workload is recorded with its full trace, attempts, tokens, latency and cost."
        actions={
          <select className="input" value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }}>
            <option value="">All sources</option>
            <option value="playground">Playground</option>
            <option value="benchmark">Benchmark</option>
          </select>
        }
      />
      <ErrorBox error={error} hint={<BackendHint />} />
      <SampleBanner show={data?.sample_data} />
      {!data && !error && <Loading />}
      {data && (
        <Card>
          {items.length === 0 ? (
            <p className="text-sm text-muted">No workloads yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="data">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Task</th>
                    <th>Category</th>
                    <th>Status</th>
                    <th>Path</th>
                    <th className="num">Tokens</th>
                    <th className="num">Latency</th>
                    <th className="num">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((w) => (
                    <tr key={w.id}>
                      <td className="whitespace-nowrap">
                        <Link className="underline" href={`/history/${w.id}`}>
                          {when(w.created_at)}
                        </Link>
                        <div className="text-xs text-muted">{w.source === "benchmark" ? `${w.case_id} · ${w.condition}` : w.source}</div>
                      </td>
                      <td className="max-w-xs truncate" title={w.task_text}>
                        {w.task_text}
                      </td>
                      <td>{w.category}</td>
                      <td>
                        <Badge tone={statusTone(w.status)}>{w.status}</Badge>
                      </td>
                      <td className="whitespace-nowrap text-xs">
                        {w.initial_tier && w.initial_tier !== w.final_tier && (
                          <>
                            <TierBadge tier={w.initial_tier} /> →{" "}
                          </>
                        )}
                        <TierBadge tier={w.final_tier} />
                      </td>
                      <td className="num">{num((w.prompt_tokens || 0) + (w.completion_tokens || 0))}</td>
                      <td className="num">{ms(w.latency_ms)}</td>
                      <td className="num">{usd(w.cost_usd, 6)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Newer
            </button>
            <button className="btn" disabled={items.length < PAGE} onClick={() => setOffset(offset + PAGE)}>
              Older
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
