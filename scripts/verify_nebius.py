#!/usr/bin/env python3
"""Acceptance Test 1 — verify a genuine Nebius Token Factory call to NVIDIA Nemotron models.

Usage (from repo root, with NEBIUS_API_KEY in .env or the environment):
    python scripts/verify_nebius.py            # catalog check + one call per tier
    python scripts/verify_nebius.py --tiers small

Prints model IDs found in the authenticated catalog, flags any configured
model that is missing, and makes one short real call per tier showing
provider-reported tokens, latency and request id. Exits non-zero on failure.
Output contains no secrets.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import load_settings  # noqa: E402
from app.providers.nebius import NebiusProvider  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", nargs="*", default=None)
    args = ap.parse_args()

    s = load_settings()
    if not s.nebius_api_key:
        print("FAIL: NEBIUS_API_KEY is not set (add it to .env at the repo root).")
        return 2
    p = NebiusProvider(s.nebius_api_key, s.nebius_base_url, s.request_timeout_s, s.max_retries)
    ok = True
    try:
        print(f"Base URL: {s.nebius_base_url}")
        models = await p.list_models()
        ids = sorted(m.get("id") for m in models if m.get("id"))
        nvidia = [i for i in ids if "nvidia" in i.lower() or "nemotron" in i.lower()]
        print(f"Catalog: {len(ids)} models; NVIDIA/Nemotron: {len(nvidia)}")
        for i in nvidia:
            print(f"  - {i}")
        for t in s.tiers:
            present = t.model_id in ids
            ok &= present
            print(f"[{'OK ' if present else 'MISSING'}] tier={t.key:6s} {t.model_id}")
        if not ok:
            print("\nFix NEBIUS_MODEL_SMALL / _MEDIUM / _LARGE in .env using IDs from the list above.")

        for t in s.tiers:
            if args.tiers and t.key not in args.tiers:
                continue
            res = await p.chat(
                t.model_id,
                [{"role": "user", "content": "What is 17 * 23? End with a line 'Answer: <number>'."}],
                max_tokens=s.max_output_tokens, temperature=0.0,
            )
            ok &= res.ok
            print(json.dumps({
                "tier": t.key, "model_requested": t.model_id, "model_reported": res.model, "ok": res.ok,
                "answer_tail": res.content[-60:] if res.content else None, "finish_reason": res.finish_reason,
                "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
                "reasoning_tokens": res.reasoning_tokens, "latency_ms": round(res.latency_ms, 1),
                "cost_usd": t.cost(res.prompt_tokens, res.completion_tokens), "request_id": res.request_id,
                "retries": res.attempts - 1, "error": res.error,
            }, indent=2))
    finally:
        await p.aclose()
    print("\nRESULT:", "PASS — genuine Nebius inference verified" if ok else "FAIL — see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
