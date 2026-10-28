#!/usr/bin/env python3
"""Run the EcoBench benchmark from the command line (same code path as the UI).

Recommended sequence for the submission (real Nebius calls):

  # 1. Calibration: gather routing evidence on the 14 calibration cases only
  python scripts/run_benchmark.py --split calib --conditions fixed:small fixed:medium fixed:large

  # 2. Held-out comparison on the 35 test cases
  python scripts/run_benchmark.py --split test --conditions fixed:large adaptive adaptive_warm fixed:small

Results are written to the SQLite DB (visible in the UI) and exported to
benchmarks/results/run-<id>-<provider>.json. Use --provider mock to dry-run offline.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def fmt(v, pct=False, usd=False):
    if v is None:
        return "—"
    if pct:
        return f"{v * 100:+.1f}%" if isinstance(v, float) and v <= 1 and v >= -1 else f"{v:.1%}"
    if usd:
        return f"${v:.5f}"
    return str(v)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["test", "calib", "all"])
    ap.add_argument("--conditions", nargs="+", default=["fixed:large", "adaptive"])
    ap.add_argument("--categories", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--provider", choices=["nebius", "mock"])
    args = ap.parse_args()
    if args.provider:
        os.environ["ECOCOMPUTE_PROVIDER"] = args.provider

    from app.benchmark.runner import BenchmarkRunner
    from app.core.config import load_settings
    from app.persistence.store import Store
    from app.providers.factory import build_provider
    from app.router.engine import EcoComputeRouter

    s = load_settings()
    store = Store(s.database_path)
    provider = build_provider(s)
    router = EcoComputeRouter(s, provider, store)
    br = BenchmarkRunner(s, router, store)
    run = br.create(conditions=args.conditions, split=args.split, categories=args.categories, limit=args.limit, repeats=args.repeats)
    print(f"Run {run['id']} · provider={provider.name} · {run['progress_total']} workloads · worst-case calls {run['config']['worst_case_calls']}")

    task = asyncio.create_task(br.wait(run["id"]))
    while not task.done():
        await asyncio.sleep(2)
        r = store.get_run(run["id"])
        print(f"  {r['progress_done']}/{r['progress_total']} workloads · {r['calls_made']} calls · ${store.spend_today_usd():.4f} spent today", flush=True)
    await task
    await provider.aclose()

    r = store.get_run(run["id"])
    summ = r["summary"]
    print(f"\nStatus: {r['status']}{' — ' + r['error'] if r['error'] else ''}")
    if summ.get("sample_data"):
        print("NOTE: mock provider — SAMPLE DATA, not real measurements.")
    print(f"\n{'condition':16s} {'n':>3s} {'pass':>6s} {'95% CI':>15s} {'cost USD':>11s} {'$/success':>11s} {'tokens/task':>11s} {'mean ms':>9s} {'esc':>5s}")
    for c, m in summ["conditions"].items():
        ci = m["success_ci95"]
        print(f"{c:16s} {m['n']:>3d} {m['success_rate']:>6.1%} {('[%.2f, %.2f]' % tuple(ci)) if ci else '—':>15s} "
              f"{fmt(m['total_cost_usd'], usd=True):>11s} {fmt(m['cost_per_success_usd'], usd=True):>11s} "
              f"{fmt(m['tokens_per_task']):>11s} {fmt(m['latency_ms_mean']):>9s} {m['escalation_rate']:>5.0%}")
    for c, cmp in summ["comparisons"].items():
        print(f"\n{c} vs {summ['baseline']} ({cmp['paired_tasks']} paired tasks):")
        print(f"  success rate diff: {cmp['success_rate_diff']:+.3f}  CI95 {cmp['success_rate_diff_ci95']}")
        print(f"  cost change:       {fmt(cmp['cost_rel_change'], pct=True)}  CI95 {cmp['cost_rel_change_ci95']}")
        print(f"  tokens change:     {fmt(cmp['tokens_rel_change'], pct=True)}  CI95 {cmp['tokens_rel_change_ci95']}")
        print(f"  latency change:    {fmt(cmp['latency_mean_rel_change'], pct=True)}  CI95 {cmp['latency_rel_change_ci95']}")
    print(f"\nExported: benchmarks/results/run-{r['id']}-{provider.name}.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
