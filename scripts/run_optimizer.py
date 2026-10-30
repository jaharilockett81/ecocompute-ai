#!/usr/bin/env python3
"""Run the EcoCompute optimization loop from the command line (same code path as the UI).

    python scripts/run_optimizer.py support-ops
    python scripts/run_optimizer.py data-pipeline --rounds 2 --no-drill
    python scripts/run_optimizer.py --upload my_workload.json

Baseline → Nemotron analysis → verification of every allowlisted proposal
(bounded refinement) → safety drill. It stops at "awaiting approval": accepting
a recommendation is a human decision (UI or POST /api/optimize/sessions/<id>/decision).
Writes benchmarks/results/optimization-<id>-<provider>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.benchmark.runner import results_dir  # noqa: E402
from app.core.config import load_settings  # noqa: E402
from app.optimizer import Optimizer, preset_workloads, validate_upload  # noqa: E402
from app.persistence.bundles import export_bundle  # noqa: E402
from app.persistence.store import Store  # noqa: E402
from app.providers.factory import build_provider  # noqa: E402
from app.router.engine import EcoComputeRouter  # noqa: E402
from app.sustainability.estimator import EnvironmentalImpactEstimator  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("preset", nargs="?", default="support-ops")
    ap.add_argument("--upload")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--no-drill", action="store_true")
    a = ap.parse_args()

    s = load_settings()
    store = Store(s.database_path)
    provider = build_provider(s)
    router = EcoComputeRouter(s, provider, store)
    opt = Optimizer(s, router, store, EnvironmentalImpactEstimator({t.key: t.active_params_b for t in s.tiers}))
    if a.upload:
        wl = {"id": "upload", "title": Path(a.upload).name, "source": "upload", "description": "uploaded",
              "cases": validate_upload(json.loads(Path(a.upload).read_text()), s)}
    else:
        wl = next((w for w in preset_workloads() if w["id"] == a.preset), None)
        if not wl:
            print(f"unknown preset {a.preset!r}; choose from {[w['id'] for w in preset_workloads()]}")
            return 2

    async def show(ev: dict) -> None:
        if ev.get("step") != "task":
            print(f"  [{ev.get('phase', ''):8s}] {ev['title']}" + (f" — {ev['detail'][:140]}" if ev.get("detail") else ""))

    try:
        oid = opt.create(wl)["state"]["id"]
        print(f"Optimization {oid} on provider {provider.name} · analyst {s.analyst_model}")
        await opt.run_baseline(oid, show)
        st = await opt.analyze(oid, show)
        valid = [p["id"] for p in (st["analysis"] or {}).get("proposals", []) if p["valid"]]
        if not valid:
            print("No valid proposal to test.", (st["analysis"] or {}).get("error") or "")
            return 1
        st = await opt.verify(oid, valid, show, max_rounds=a.rounds, safety_drill=not a.no_drill)
    finally:
        await provider.aclose()

    if provider.name != "nebius":
        print("\nNOTE: mock provider — SAMPLE DATA, not real measurements.")
    b = st["baseline"]["totals"]
    print(f"\nBaseline: {b['passed']}/{b['tasks']} passed, cost {b['cost_usd']}, tokens {b['total_tokens']}, model time {b['model_latency_ms']} ms")
    for r in st["rounds"]:
        t = r["run"]["totals"]
        print(f"Round {r['round']}: gate {'ACCEPTED' if r['gate']['accepted'] else 'REJECTED'}; {t['passed']}/{t['tasks']} passed, "
              f"cost {t['cost_usd']}, tokens {t['total_tokens']}; deltas {json.dumps(r['gate']['deltas'])}")
    if st.get("drill") and st["drill"].get("gate"):
        print(f"Safety drill: gate {'REJECTED (expected)' if not st['drill']['gate']['accepted'] else 'ACCEPTED (gate defect!)'}")
    print(f"Status: {st['status']}")
    out = results_dir()
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"optimization-{oid}-{provider.name}.json"
    path.write_text(json.dumps(export_bundle(store, "optimization", oid), indent=2, default=str))
    print(f"Evidence bundle: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
