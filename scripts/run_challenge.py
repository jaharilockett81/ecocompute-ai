#!/usr/bin/env python3
"""Run The EcoCompute Challenge from the command line (same code path as the UI).

    python scripts/run_challenge.py routine
    python scripts/run_challenge.py demanding

Uses the configured provider (Nebius when NEBIUS_API_KEY is set). The run is
stored in the SQLite DB, so it also appears on the Challenge page.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.challenge import SCENARIO_MAP, run_challenge  # noqa: E402
from app.core.config import load_settings  # noqa: E402
from app.persistence.store import Store  # noqa: E402
from app.providers.factory import build_provider  # noqa: E402
from app.router.engine import EcoComputeRouter  # noqa: E402


async def main() -> int:
    sid = sys.argv[1] if len(sys.argv) > 1 else "routine"
    if sid not in SCENARIO_MAP:
        print(f"unknown scenario {sid!r}; choose from {sorted(SCENARIO_MAP)}")
        return 2
    s = load_settings()
    store = Store(s.database_path)
    provider = build_provider(s)
    router = EcoComputeRouter(s, provider, store)

    async def show(ev: dict) -> None:
        if ev.get("lane") and ev.get("step") in ("select", "infer", "evaluate", "escalate", "final") and ev.get("status") != "running":
            print(f"  [{ev['lane']:10s}] {ev['step']:9s} {ev['title']}" + (f" — {ev['detail'][:100]}" if ev.get("detail") else ""))

    try:
        c = await run_challenge(s, router, store, sid, show)
    finally:
        await provider.aclose()
    cmp = c["comparison"]
    if cmp["sample_data"]:
        print("\nNOTE: mock provider — SAMPLE DATA, not real measurements.")
    print(f"\n{cmp['what_happened']}\n{cmp['verdict']}\n")
    for name, ln in cmp["lanes"].items():
        print(f"{name:10s} passed={ln['passed']!s:5s} path={ln['initial_tier']}->{ln['final_tier']} calls={ln['calls']} "
              f"tokens={ln['total_tokens']} wall_ms={ln['wall_ms']} cost={ln['total_cost_usd']}")
        for call in ln["call_log"]:
            print(f"    {call['provider']} {call['model']} request_id={call['request_id']} validator_passed={call.get('validator_passed')}")
    print(f"\nChallenge id: {c['id']}")
    print(json.dumps(cmp["deltas"]))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
