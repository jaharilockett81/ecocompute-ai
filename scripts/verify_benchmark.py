#!/usr/bin/env python3
"""Independently re-check committed benchmark bundles (no network, no API key).

    python scripts/verify_benchmark.py

For every real-provider run in benchmarks/results it checks that:
  * calibration and held-out case IDs are disjoint, and a test run used only test cases;
  * cost recomputed from raw provider token counts x configured prices equals the stored cost;
  * cold `adaptive` routing used no observed evidence, and `adaptive_warm` evidence counts
    match calibration-run attempts only (no test-set leakage);
  * every call carries a provider request ID;
  * provider errors are listed separately from quality failures.
Then it prints the cost change vs the baseline computed from the raw records.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICES = {"small": (0.06, 0.24), "medium": (0.30, 0.90), "large": (1.00, 3.00)}  # $/1M tokens, as in render.yaml


def main() -> int:
    ds = json.loads((ROOT / "benchmarks/datasets/ecobench-v1.json").read_text())
    calib = {c["id"] for c in ds["cases"] if c["split"] == "calib"}
    test = {c["id"] for c in ds["cases"] if c["split"] == "test"}
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        ok &= cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")

    print(f"Dataset: {len(calib)} calibration, {len(test)} held-out cases")
    check(not (calib & test), "calibration and held-out case IDs are disjoint")
    runs = sorted((json.loads(p.read_text()) for p in (ROOT / "benchmarks/results").glob("run-*-nebius.json")),
                  key=lambda b: b["record"]["created_at"])
    calib_attempts: dict[tuple[str, str], int] = defaultdict(int)

    for b in runs:
        r, wls = b["record"], b["workloads"]
        split = r["config"]["split"]
        print(f"\nRun {r['id']} ({split}, {len(wls)} workloads, conditions {', '.join(r['conditions'])})")
        check(set(r["case_ids"]) <= (calib if split == "calib" else test), f"only {split} cases used")
        cost, recomputed, calls, ids = defaultdict(float), defaultdict(float), 0, 0
        errors, failures = [], []
        for w in wls:
            cost[w["condition"]] += w["cost_usd"] or 0
            for a in w["attempts"]:
                calls += 1
                if a["ok"] and a["prompt_tokens"] is not None:
                    pi, po = PRICES[a["tier"]]
                    recomputed[w["condition"]] += (a["prompt_tokens"] * pi + a["completion_tokens"] * po) / 1e6
                else:
                    errors.append(f"{w['condition']} {w['case_id']} {a['tier']}: {(a['error'] or '')[:60]}")
            if w["status"] != "passed":
                failures.append(f"{w['condition']} {w['case_id']}")
            ids += len(set(re.findall(r"chatcmpl-[0-9a-f]+", json.dumps(w["trace"]))))
        check(all(abs(cost[c] - recomputed[c]) < 1e-6 for c in cost), "stored cost == provider tokens x configured prices")
        check(ids >= calls - len(errors), f"provider request IDs present ({ids} for {calls} calls)")
        for w in wls:
            if w["condition"] == "adaptive":
                if any(e["observed_n"] for e in w["decision"]["estimates"]):
                    check(False, f"cold adaptive used evidence on {w['case_id']}")
                    break
        if split == "test" and "adaptive_warm" in r["conditions"]:
            seen = {(w["category"], e["tier"]): e["observed_n"] for w in wls if w["condition"] == "adaptive_warm"
                    for e in w["decision"]["estimates"]}
            if not any(seen.values()):
                print("  [NOTE] adaptive_warm had no calibration evidence in this run (it ran before calibration); it behaves as cold")
            else:
                check(all(n <= calib_attempts[k] for k, n in seen.items()), "warm evidence counts <= calibration attempts (no test leakage)")
        if split == "calib":
            for w in wls:
                for a in w["attempts"]:
                    calib_attempts[(w["category"], a["tier"])] += 1
        base = cost.get("fixed:large")
        for c in r["conditions"]:
            delta = f"{(cost[c] / base - 1) * 100:+.1f}% vs fixed:large" if base and c != "fixed:large" else "baseline" if c == "fixed:large" else ""
            print(f"    {c:14s} ${cost[c]:.6f}  {delta}")
        if errors:
            print("    provider errors (not quality failures): " + "; ".join(errors))
        print("    non-passing workloads: " + (", ".join(failures) or "none"))

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
