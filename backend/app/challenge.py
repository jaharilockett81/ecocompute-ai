"""The EcoCompute Challenge: one task, two lanes, real inference.

Lane "ecocompute" runs the task through the router (policy-selected start
tier, validation, escalation on genuine failure). Lane "baseline" runs the
same task, with the same quality requirement, on the fixed baseline tier with
no escalation. Both lanes are recorded as ordinary workloads (source
"challenge"), and the comparison is computed only from those records.

Nothing here steers a model towards failure. The scenarios differ only in the
task: one is routine, one is genuinely demanding for a small model. Whether
escalation happens is decided by the validator on the actual output, and the
outcome is reported as observed.

Routing uses the prior only (evidence_override={}) so a run is reproducible
and is not influenced by earlier playground traffic.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Awaitable, Callable

from app.api.presets import PRESETS
from app.core.config import Settings
from app.benchmark.runner import results_dir
from app.persistence.bundles import export_bundle
from app.persistence.store import Store
from app.router.engine import EcoComputeRouter, WorkloadSpec
from app.schemas.api import WorkloadRequest

Emit = Callable[[dict], Awaitable[None]]

_STRICT = next(p for p in PRESETS if p["id"] == "strict-extraction")["request"]


def _checks(**req) -> list[dict]:
    return WorkloadRequest(**req).build_checks()


SCENARIOS: list[dict] = [
    {
        "id": "routine",
        "title": "Routine triage",
        "kind": "first_attempt",
        "blurb": "Everyday support-ticket triage. A small model should handle this, so the router starts small and the validator decides whether that was enough.",
        "requirement": "Valid JSON with exactly the keys ticket_1..ticket_3, each equal to the correct team.",
        "task": (
            "Route each support ticket to exactly one team: billing, technical, account, or shipping. "
            "Return JSON {\"ticket_1\": team, \"ticket_2\": team, \"ticket_3\": team}.\n\n"
            "ticket_1: \"I was charged twice for my October subscription.\"\n"
            "ticket_2: \"The app crashes every time I open the settings screen.\"\n"
            "ticket_3: \"Tracking says delivered but the box never arrived.\""
        ),
        "category": "classification",
        "output_format": "json",
        "quality_threshold": 0.8,
        "checks": _checks(
            task="x" * 3, output_format="json",
            json_schema={"type": "object", "required": ["ticket_1", "ticket_2", "ticket_3"], "additionalProperties": False,
                         "properties": {k: {"enum": ["billing", "technical", "account", "shipping"]} for k in ("ticket_1", "ticket_2", "ticket_3")}},
            expected_fields={"ticket_1": "billing", "ticket_2": "technical", "ticket_3": "shipping"},
        ),
    },
    {
        "id": "demanding",
        "title": "Demanding extraction",
        "kind": "escalation_prone",
        "blurb": "Strict schema extraction with time conversion, duration arithmetic and status inference. Hard for a small model; if its answer fails the validator, the router escalates.",
        "requirement": "JSON matching a strict schema (4 shipments, IATA codes, ISO 24h times, enum status, integer delays, booleans) with 12 fields equal to the correct values.",
        "task": _STRICT["task"],
        "category": _STRICT["category"],
        "output_format": _STRICT["output_format"],
        "quality_threshold": _STRICT.get("quality_threshold", 0.85),
        "checks": _checks(task=_STRICT["task"], output_format="json", json_schema=_STRICT["json_schema"],
                          expected_fields=_STRICT["expected_fields"]),
    },
]
SCENARIO_MAP = {s["id"]: s for s in SCENARIOS}


def public_scenarios(settings: Settings) -> list[dict]:
    base = settings.tier_map[settings.baseline_tier]
    return [{**s, "baseline": {"tier": base.key, "label": base.label, "model_id": base.model_id}} for s in SCENARIOS]


# ------------------------------------------------------------------ metrics
def _lane_metrics(w: dict, wall_ms: float) -> dict:
    trace = w.get("trace") or []
    calls, evaluations = [], []
    routing_ms = eval_ms = 0.0
    start_ts = next((e["ts"] for e in trace if e["step"] == "start"), None)
    select_ts = next((e["ts"] for e in trace if e["step"] == "select"), None)
    if start_ts and select_ts:
        routing_ms = (select_ts - start_ts) * 1000
    last_infer_ts = None
    for e in trace:
        d = e.get("data") or {}
        if e["step"] == "infer" and e["status"] in ("done", "failed"):
            last_infer_ts = e["ts"]
            calls.append({k: d.get(k) for k in ("tier", "model", "provider", "ok", "prompt_tokens", "completion_tokens",
                                                "reasoning_tokens", "latency_ms", "cost_usd", "finish_reason", "request_id", "error")})
        elif e["step"] == "evaluate" and e["status"] in ("done", "failed"):
            if last_infer_ts:
                eval_ms += (e["ts"] - last_infer_ts) * 1000
            evaluations.append({"tier": calls[-1]["tier"] if calls else None, "passed": d.get("passed"),
                                "method": d.get("method"), "detail": e.get("detail")})
            if calls:
                calls[-1]["validator_passed"] = d.get("passed")
    attempts = w.get("attempts") or []
    overhead_calls = [a for a in attempts if a.get("role") in ("judge", "router")]
    total_cost = w.get("cost_usd")
    overhead_cost = w.get("overhead_cost_usd") or 0.0
    esc = w.get("escalations") or 0
    status = w.get("status")
    if status == "passed":
        outcome = "first_attempt_pass" if esc == 0 else "escalated_then_passed"
    elif status == "failed":
        outcome = "failed_no_escalation" if esc == 0 else "escalated_still_failed"
    else:
        outcome = status
    tokens = (w.get("prompt_tokens") or 0) + (w.get("completion_tokens") or 0)
    return {
        "workload_id": w["id"],
        "status": status,
        "passed": status == "passed",
        "outcome": outcome,
        "initial_tier": w.get("initial_tier"),
        "final_tier": w.get("final_tier"),
        "final_model": w.get("final_model"),
        "started_below_baseline": None,
        "escalations": esc,
        "calls": len(calls),
        "call_log": calls,
        "evaluations": evaluations,
        "final_evaluation": evaluations[-1] if evaluations else None,
        "prompt_tokens": w.get("prompt_tokens"),
        "completion_tokens": w.get("completion_tokens"),
        "reasoning_tokens": w.get("reasoning_tokens"),
        "total_tokens": tokens,
        "usage_complete": bool(w.get("usage_complete")),
        "model_latency_ms": w.get("latency_ms"),
        "wall_ms": round(wall_ms, 1),
        "inference_cost_usd": None if total_cost is None else round(total_cost - overhead_cost, 8),
        "overhead": {
            "routing_ms": round(routing_ms, 2),
            "evaluation_ms": round(eval_ms, 2),
            "paid_overhead_calls": len(overhead_calls),
            "overhead_cost_usd": round(overhead_cost, 8),
            "note": "Routing is rule-based and evaluation is deterministic, so neither makes a paid model call; their cost is $0 and their local compute time is measured from the trace.",
        },
        "total_cost_usd": total_cost,
        "provider": w.get("provider"),
    }


def _rel(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return round(a / b - 1, 4)


def compare(eco: dict, base: dict) -> dict:
    deltas = {
        "cost_rel": _rel(eco["total_cost_usd"], base["total_cost_usd"]),
        "tokens_rel": _rel(eco["total_tokens"], base["total_tokens"]),
        "wall_latency_rel": _rel(eco["wall_ms"], base["wall_ms"]),
        "model_latency_rel": _rel(eco["model_latency_ms"], base["model_latency_ms"]),
    }
    cost_known = eco["total_cost_usd"] is not None and base["total_cost_usd"] is not None
    metric = "cost" if cost_known else "tokens"
    d = deltas["cost_rel"] if cost_known else deltas["tokens_rel"]
    pct = f"{abs(d) * 100:.0f}%" if d is not None else "an unknown amount"
    lat = deltas["wall_latency_rel"]
    lat_txt = "" if lat is None else f" End-to-end latency was {abs(lat) * 100:.0f}% {'lower' if lat < 0 else 'higher'}."
    if eco["passed"] and base["passed"]:
        if d is not None and d < 0:
            verdict, improved = f"Improved: both met the requirement, and EcoCompute used {pct} less {metric}.{lat_txt}", True
        else:
            verdict, improved = (f"No improvement: both met the requirement, but EcoCompute used {pct} more {metric}"
                                 f"{' because it escalated' if eco['escalations'] else ''}.{lat_txt}"), False
    elif eco["passed"] and not base["passed"]:
        verdict, improved = f"Better quality: EcoCompute met the requirement and the fixed baseline did not ({metric} {'+' if (d or 0) > 0 else '−'}{pct}).{lat_txt}", True
    elif base["passed"] and not eco["passed"]:
        verdict, improved = f"Tradeoff: the fixed baseline met the requirement and EcoCompute did not, so its {metric} saving does not count as an improvement.{lat_txt}", False
    else:
        verdict, improved = "Neither lane met the requirement on this run.", False
    if not cost_known:
        verdict += " (Cost unavailable because prices are not configured; compared on tokens.)"
    return {"deltas": deltas, "compared_on": metric, "improved": improved, "verdict": verdict}


def what_happened(eco: dict, scenario: dict, labels: dict[str, str]) -> str:
    start, final = labels.get(eco["initial_tier"], eco["initial_tier"]), labels.get(eco["final_tier"], eco["final_tier"])
    o = eco["outcome"]
    if o == "first_attempt_pass":
        s = f"The router started on {start} and its first answer passed the validator, so no escalation was needed."
        if scenario["kind"] == "escalation_prone":
            s += " This scenario is designed to be hard for a small model, but escalation is never forced: on this run the small model succeeded."
        return s
    if o == "escalated_then_passed":
        return f"The router started on {start}. The validator rejected that answer, so it escalated and {final}'s answer passed the same requirement."
    if o == "escalated_still_failed":
        return f"The router started on {start}, escalated after a validator failure, and {final}'s answer also failed the requirement."
    if o == "failed_no_escalation":
        return f"The router started on {start}; the answer failed the validator and no stronger tier was available in the chain."
    return f"The workload ended with status '{o}'."


# ------------------------------------------------------------------ runner
async def run_challenge(settings: Settings, router: EcoComputeRouter, store: Store, scenario_id: str,
                        emit: Emit | None = None) -> dict:
    sc = SCENARIO_MAP[scenario_id]
    provider = router.provider.name
    cid = store.create_challenge(scenario_id=scenario_id, provider=provider)
    if emit:
        await emit({"lane": None, "step": "challenge", "challenge_id": cid, "scenario_id": scenario_id, "provider": provider})

    common = dict(task=sc["task"], category=sc["category"], output_format=sc["output_format"], checks=sc["checks"],
                  quality_threshold=sc["quality_threshold"], max_escalations=2, repair_attempts=0,
                  source="challenge", run_id=cid, case_id=scenario_id, evidence_override={})
    specs = {
        "ecocompute": WorkloadSpec(**common, allow_escalation=True, condition="ecocompute"),
        "baseline": WorkloadSpec(**common, allow_escalation=False, forced_tier=settings.baseline_tier, condition=f"fixed:{settings.baseline_tier}"),
    }

    async def lane(name: str):
        async def lane_emit(ev: dict) -> None:
            if emit:
                await emit({**ev, "lane": name})
        t0 = time.perf_counter()
        out = await router.run(specs[name], lane_emit)
        return out, (time.perf_counter() - t0) * 1000

    try:
        (eco_out, eco_ms), (base_out, base_ms) = await asyncio.gather(lane("ecocompute"), lane("baseline"))
    except Exception as exc:
        store.update_challenge(cid, status="failed", finished_at=time.time(), error=f"{type(exc).__name__}: {exc}")
        raise

    rank = {t.key: t.rank for t in settings.tiers}
    labels = {t.key: t.label for t in settings.tiers}
    eco = _lane_metrics(store.get_workload(eco_out.workload_id), eco_ms)
    base = _lane_metrics(store.get_workload(base_out.workload_id), base_ms)
    eco["started_below_baseline"] = rank.get(eco["initial_tier"], 99) < rank[settings.baseline_tier]
    comparison = {
        "scenario": {k: sc[k] for k in ("id", "title", "kind", "requirement")},
        "provider": provider,
        "sample_data": provider != "nebius",
        "baseline_tier": settings.baseline_tier,
        "lanes": {"ecocompute": eco, "baseline": base},
        "what_happened": what_happened(eco, sc, labels),
        **compare(eco, base),
    }
    store.update_challenge(cid, status="completed", finished_at=time.time(), ecocompute_workload_id=eco["workload_id"],
                           baseline_workload_id=base["workload_id"], comparison_json=comparison)
    try:
        out = results_dir()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"challenge-{cid}-{provider}.json").write_text(json.dumps(export_bundle(store, "challenge", cid), indent=2, default=str))
    except Exception:  # export is a convenience; the DB record is authoritative
        pass
    return store.get_challenge(cid)
