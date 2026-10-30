"""EcoCompute Optimizer: a Nemotron agent that removes wasted inference compute
from a recurring AI workload, with verification that does not trust the model.

    observe   run the workload on its current configuration (baseline) and profile it
    reason    Nemotron reads the measured profile and diagnoses inefficiencies
    propose   it returns structured, bounded interventions from a fixed allowlist
    approve   a human picks which proposals may be tested (the test spends money)
    execute   the candidate configuration runs on the same workload
    measure   tokens, cost, latency, CPU time, calls, estimated energy
    verify    a deterministic gate compares candidate vs baseline task by task
    refine    on rejection, the measured regressions go back to Nemotron (bounded rounds)
    decide    a verified recommendation waits for a human to accept, reject or export

The agent never executes code it writes and never edits the live router. Its
only power is to propose values for three configuration knobs, which are
validated against an allowlist before anything runs. Whether a proposal is
kept is decided by measurements and validators, never by the model.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Awaitable, Callable

import jsonschema

from app.benchmark.runner import load_dataset
from app.core.config import Settings
from app.evaluation.validators import parse_json_output
from app.persistence.store import Store
from app.providers.base import split_reasoning
from app.router.analyzer import CATEGORIES
from app.router.engine import EcoComputeRouter, WorkloadSpec
from app.sustainability.estimator import EnvironmentalImpactEstimator

Emit = Callable[[dict], Awaitable[None]]

ANALYST_MARK = "You are EcoCompute's optimization analyst"
ALLOWED_TYPES = ("route_category", "cap_output_tokens", "enable_escalation")
MIN_CAP = 16
MAX_ROUNDS = 3
MAX_UPLOAD_CASES = 20
CHECK_TYPES = ("json_schema", "json_fields", "exact", "label", "numeric", "contains_all", "excludes", "word_limit",
               "bullet_count", "regex", "python_tests")
NOT_OBSERVABLE = {
    "gpu_utilization": "not observable: Nebius Token Factory is a serverless API and exposes no GPU telemetry",
    "gpu_memory": "not observable through a serverless API",
    "measured_energy": "not available: no power readings; energy is a FLOPs-based estimate",
}

# ------------------------------------------------------------------ workloads
_PRESET_DEFS = [
    {"id": "support-ops", "title": "Support ops nightly batch",
     "description": "Ticket classification and field extraction that a support team runs every night on its largest model.",
     "picks": {"classification": 4, "extraction": 4}},
    {"id": "data-pipeline", "title": "Data pipeline enrichment",
     "description": "Structured-JSON generation and numeric data interpretation inside an ETL job.",
     "picks": {"structured_json": 4, "data_interpretation": 4}},
    {"id": "mixed-agent", "title": "Mixed agent workload",
     "description": "Reasoning, small coding tasks (checked by unit tests in a sandbox) and summaries.",
     "picks": {"reasoning": 3, "coding": 3, "summarization": 2}},
]


def preset_workloads() -> list[dict]:
    cases = load_dataset()["cases"]
    out = []
    for d in _PRESET_DEFS:
        picked = []
        for cat, n in d["picks"].items():
            picked += sorted((c for c in cases if c["category"] == cat), key=lambda c: c["id"])[:n]
        out.append({"id": d["id"], "title": d["title"], "description": d["description"], "source": "preset",
                    "cases": [{k: c[k] for k in ("id", "category", "output_format", "task", "checks")} for c in picked]})
    return out


def validate_upload(raw: object, settings: Settings) -> list[dict]:
    """Uploaded workloads use the EcoBench case format. Every case must carry a deterministic check."""
    items = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ValueError("expected a JSON list of cases (or {\"cases\": [...]})")
    if len(items) > MAX_UPLOAD_CASES:
        raise ValueError(f"at most {MAX_UPLOAD_CASES} cases per workload")
    out = []
    for i, c in enumerate(items):
        where = f"case {i + 1}"
        if not isinstance(c, dict) or not isinstance(c.get("task"), str) or not c["task"].strip():
            raise ValueError(f"{where}: 'task' (non-empty string) is required")
        if len(c["task"]) > settings.max_task_chars:
            raise ValueError(f"{where}: task longer than {settings.max_task_chars} characters")
        cat = c.get("category") or "general"
        if cat not in CATEGORIES:
            raise ValueError(f"{where}: category must be one of {', '.join(CATEGORIES)}")
        fmt = c.get("output_format") or "text"
        if fmt not in ("text", "json", "code"):
            raise ValueError(f"{where}: output_format must be text, json or code")
        checks = c.get("checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"{where}: at least one deterministic check is required (the gate cannot verify without one)")
        for ch in checks:
            if not isinstance(ch, dict) or ch.get("type") not in CHECK_TYPES:
                raise ValueError(f"{where}: unknown check type {ch.get('type') if isinstance(ch, dict) else ch!r}")
            if ch["type"] == "python_tests" and not settings.enable_code_execution:
                raise ValueError(f"{where}: python_tests checks are disabled on this server")
        out.append({"id": str(c.get("id") or f"case-{i + 1}")[:40], "category": cat, "output_format": fmt,
                    "task": c["task"], "checks": checks})
    if len({c["id"] for c in out}) != len(out):
        raise ValueError("case ids must be unique")
    return out


# ------------------------------------------------------------------ config
def baseline_config(settings: Settings) -> dict:
    return {"default": {"tier": settings.baseline_tier, "max_output_tokens": settings.max_output_tokens, "escalation": False},
            "per_category": {}}


def resolve(config: dict, category: str) -> dict:
    return {**config["default"], **config["per_category"].get(category, {})}


def apply_proposals(config: dict, proposals: list[dict], categories: list[str]) -> dict:
    cfg = json.loads(json.dumps(config))
    for p in proposals:
        for cat in (categories if p["category"] == "*" else [p["category"]]):
            slot = cfg["per_category"].setdefault(cat, {})
            if p["type"] == "route_category":
                slot["tier"] = p["tier"]
            elif p["type"] == "cap_output_tokens":
                slot["max_output_tokens"] = int(p["max_output_tokens"])
            elif p["type"] == "enable_escalation":
                slot["escalation"] = bool(p["enabled"])
    return cfg


# ------------------------------------------------------------------ analyst I/O
ANALYST_SCHEMA = {
    "type": "object",
    "required": ["diagnosis", "proposals"],
    "properties": {
        "diagnosis": {"type": "array", "maxItems": 10, "items": {
            "type": "object", "required": ["finding", "evidence"],
            "properties": {"finding": {"type": "string"}, "evidence": {"type": "string"},
                           "categories": {"type": "array", "items": {"type": "string"}}}}},
        "proposals": {"type": "array", "maxItems": 12, "items": {"type": "object", "required": ["type"]}},
        "next_action": {"type": "string"},
    },
}


def validate_proposal(p: object, settings: Settings, categories: list[str]) -> tuple[dict, str | None]:
    """Independent of the model: return (normalised proposal, rejection reason or None)."""
    if not isinstance(p, dict):
        return {"type": "invalid", "raw": p}, "not an object"
    q = {k: p.get(k) for k in ("id", "type", "category", "tier", "max_output_tokens", "enabled",
                                "rationale", "evidence", "expected_effect", "risk", "injected")}
    q = {k: v for k, v in q.items() if v is not None}
    q["category"] = q.get("category") or "*"
    if q.get("type") not in ALLOWED_TYPES:
        extra = {k: p[k] for k in p if k not in q}
        if extra:
            q["requested"] = extra
        return q, f"'{q.get('type')}' is not an allowed intervention (allowed: {', '.join(ALLOWED_TYPES)}); nothing was executed"
    if q["category"] != "*" and q["category"] not in categories:
        return q, f"category '{q['category']}' is not in this workload"
    if q["type"] == "route_category" and q.get("tier") not in settings.tier_map:
        return q, f"unknown tier {q.get('tier')!r}"
    if q["type"] == "cap_output_tokens":
        v = q.get("max_output_tokens")
        if not isinstance(v, int) or isinstance(v, bool) or not MIN_CAP <= v <= settings.max_output_tokens:
            return q, f"max_output_tokens must be an integer between {MIN_CAP} and {settings.max_output_tokens}"
    if q["type"] == "enable_escalation" and not isinstance(q.get("enabled"), bool):
        return q, "enabled must be true or false"
    for k in ("rationale", "evidence", "expected_effect", "risk"):
        if k in q:
            q[k] = str(q[k])[:600]
    return q, None


def build_profile(settings: Settings, cases: list[dict], run: dict) -> dict:
    """Measured evidence the analyst reasons over. Only observed numbers, no guesses."""
    by_cat: dict[str, dict] = {}
    for r in run["rows"]:
        c = by_cat.setdefault(r["category"], {"n": 0, "passed": 0, "completion_tokens": [], "reasoning_tokens": [],
                                              "latency_ms": [], "cost_usd": 0.0, "truncated": 0, "tiers": {}})
        c["n"] += 1
        c["passed"] += int(bool(r["passed"]))
        c["completion_tokens"].append(r.get("completion_tokens") or 0)
        c["reasoning_tokens"].append(r.get("reasoning_tokens") or 0)
        c["latency_ms"].append(r.get("latency_ms") or 0)
        c["cost_usd"] += r.get("cost_usd") or 0
        c["truncated"] += int(r.get("finish_reason") == "length")
        c["tiers"][r.get("final_tier")] = c["tiers"].get(r.get("final_tier"), 0) + 1
    cats = {}
    for k, c in by_cat.items():
        ct = c["completion_tokens"]
        cats[k] = {"tasks": c["n"], "passed": c["passed"], "mean_completion_tokens": round(sum(ct) / len(ct), 1),
                   "max_completion_tokens": max(ct), "mean_reasoning_tokens": round(sum(c["reasoning_tokens"]) / c["n"], 1),
                   "mean_latency_ms": round(sum(c["latency_ms"]) / c["n"], 1), "cost_usd": round(c["cost_usd"], 6),
                   "truncated_answers": c["truncated"], "final_tiers": c["tiers"]}
    return {
        "workload_tasks": len(cases),
        "current_config": run["config"],
        "totals": {k: run["totals"].get(k) for k in ("passed", "tasks", "cost_usd", "total_tokens", "model_latency_ms", "calls")},
        "categories": cats,
        "tiers": [{"key": t.key, "model": t.model_id, "active_params_b": t.active_params_b,
                   "usd_per_1m_input": t.price_in_per_m, "usd_per_1m_output": t.price_out_per_m} for t in settings.tiers],
    }


def analyst_messages(profile: dict, feedback: dict | None, max_tokens_limit: int) -> list[dict]:
    system = (
        f"{ANALYST_MARK}. You reduce wasted inference compute in a recurring AI workload without lowering quality. "
        "You can only change three knobs per task category: route_category (which model tier answers), "
        f"cap_output_tokens ({MIN_CAP}..{max_tokens_limit}) and enable_escalation (retry on the next larger tier when a "
        "deterministic validator rejects an answer). You cannot run code or commands. "
        "Every task has a deterministic validator; a proposal is only kept if no task that passed before fails afterwards "
        "and total cost goes down, as measured. Prefer few, well-evidenced proposals. "
        "Respond with ONLY a JSON object: {\"diagnosis\": [{\"finding\", \"evidence\", \"categories\"}], "
        "\"proposals\": [{\"id\", \"type\", \"category\" (a category or \"*\"), \"tier\" | \"max_output_tokens\" | \"enabled\", "
        "\"rationale\", \"evidence\", \"expected_effect\", \"risk\"}], \"next_action\"}. Cite the measured numbers you used."
    )
    user = "CATEGORIES: " + ",".join(profile["categories"]) + "\n\nMEASURED PROFILE:\n" + json.dumps(profile, indent=1)
    if feedback:
        user += ("\n\nYOUR PREVIOUS PROPOSALS WERE TESTED AND REJECTED BY THE VERIFICATION GATE. "
                 "Revise them using this measured feedback (keep what worked, drop or weaken what caused regressions):\n"
                 + json.dumps(feedback, indent=1))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def call_analyst(router: EcoComputeRouter, settings: Settings, messages: list[dict]) -> dict:
    """One Nemotron call with structured output. Falls back to plain JSON prompting if the
    endpoint rejects response_format. Returns parsed output plus call metadata."""
    model = settings.analyst_model
    tier = settings.tier_for_model(model)
    max_tokens = max(4096, settings.max_output_tokens)
    res = await router.provider.chat(model, messages, max_tokens=max_tokens, temperature=0.0,
                                     response_format={"type": "json_object"})
    used_rf = True
    if not res.ok and res.error_type not in ("auth", "configuration", "timeout"):
        res = await router.provider.chat(model, messages, max_tokens=max_tokens, temperature=0.0)
        used_rf = False
    cost = tier.cost(res.prompt_tokens, res.completion_tokens) if tier and res.ok else None
    meta = {"model": res.model or model, "provider": res.provider, "ok": res.ok, "request_id": res.request_id,
            "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
            "reasoning_tokens": res.reasoning_tokens, "latency_ms": round(res.latency_ms, 1), "cost_usd": cost,
            "finish_reason": res.finish_reason, "structured_output": used_rf, "error": res.error, "tier": tier.key if tier else None}
    if not res.ok:
        return {"call": meta, "parsed": None, "error": res.error or "analyst call failed"}
    answer, _ = split_reasoning(res.content)
    data, err = parse_json_output(answer)
    if err:
        return {"call": meta, "parsed": None, "error": f"analyst output was not valid JSON: {err}", "raw": answer[:2000]}
    try:
        jsonschema.validate(data, ANALYST_SCHEMA)
    except jsonschema.ValidationError as exc:
        return {"call": meta, "parsed": None, "error": f"analyst output failed the schema: {exc.message}", "raw": answer[:2000]}
    return {"call": meta, "parsed": data, "error": None}


# ------------------------------------------------------------------ execution
async def execute(settings: Settings, router: EcoComputeRouter, store: Store, impact: EnvironmentalImpactEstimator,
                  cases: list[dict], config: dict, label: str, oid: str, emit: Emit) -> dict:
    t_wall, t_cpu = time.perf_counter(), time.process_time()
    done = 0

    async def one(case: dict) -> dict:
        nonlocal done
        knobs = resolve(config, case["category"])
        spec = WorkloadSpec(task=case["task"], category=case["category"], output_format=case["output_format"],
                            checks=case["checks"], forced_tier=knobs["tier"], allow_escalation=bool(knobs["escalation"]),
                            max_escalations=2, max_output_tokens=int(knobs["max_output_tokens"]), repair_attempts=0,
                            source="optimizer", run_id=oid, condition=label, case_id=case["id"], evidence_override={})
        out = await router.run(spec)
        w = store.get_workload(out.workload_id)
        primary = [a for a in w.get("attempts") or [] if a.get("role") == "primary"]
        row = {"case_id": case["id"], "category": case["category"], "workload_id": out.workload_id, "status": out.status,
               "passed": out.status == "passed", "initial_tier": knobs["tier"], "final_tier": out.final_tier,
               "calls": out.totals["calls"], "escalations": out.totals["escalations"],
               "prompt_tokens": out.totals["prompt_tokens"], "completion_tokens": out.totals["completion_tokens"],
               "reasoning_tokens": out.totals["reasoning_tokens"], "latency_ms": round(out.totals["latency_ms"], 1),
               "cost_usd": round(out.totals["cost_usd"], 8) if out.totals["cost_complete"] else None,
               "finish_reason": primary[-1].get("finish_reason") if primary else None,
               "eval_detail": (out.eval or {}).get("detail", "")[:300], "attempts": primary}
        done += 1
        await emit({"step": "task", "status": "done" if row["passed"] else "failed", "run": label,
                    "title": f"{case['id']} {'passed' if row['passed'] else out.status}",
                    "detail": f"{knobs['tier']}→{out.final_tier} · {row['completion_tokens']} out tokens · {row['latency_ms']:.0f} ms",
                    "data": {"done": done, "total": len(cases), "case_id": case["id"], "passed": row["passed"]}})
        return row

    rows = await asyncio.gather(*(one(c) for c in cases))
    wall_ms = (time.perf_counter() - t_wall) * 1000
    cpu_ms = (time.process_time() - t_cpu) * 1000
    attempts = [a for r in rows for a in r.pop("attempts")]
    costs = [r["cost_usd"] for r in rows]
    totals = {
        "tasks": len(rows), "passed": sum(r["passed"] for r in rows),
        "errors": sum(r["status"] in ("error", "budget_blocked") for r in rows),
        "calls": sum(r["calls"] for r in rows), "escalations": sum(r["escalations"] for r in rows),
        "prompt_tokens": sum(r["prompt_tokens"] for r in rows), "completion_tokens": sum(r["completion_tokens"] for r in rows),
        "reasoning_tokens": sum(r["reasoning_tokens"] for r in rows),
        "cost_usd": None if any(c is None for c in costs) else round(sum(costs), 8),
        "model_latency_ms": round(sum(r["latency_ms"] for r in rows), 1),
        "wall_ms": round(wall_ms, 1), "backend_cpu_ms": round(cpu_ms, 1),
    }
    totals["total_tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
    totals["pass_rate"] = round(totals["passed"] / max(1, totals["tasks"]), 4)
    est = impact.estimate_attempts(attempts)
    return {"label": label, "config": config, "rows": rows, "totals": totals, "energy_estimate": est,
            "provider": router.provider.name, "measured_at": time.time(),
            "measurement_notes": {"backend_cpu_ms": "CPU time of the EcoCompute backend process (orchestration + validation), not model compute",
                                  **NOT_OBSERVABLE}}


def gate(base: dict, cand: dict) -> dict:
    """Deterministic acceptance gate. It never consults a model."""
    b = {r["case_id"]: r for r in base["rows"]}
    regressions = [{"case_id": r["case_id"], "category": r["category"], "detail": r["eval_detail"], "final_tier": r["final_tier"],
                    "finish_reason": r["finish_reason"]}
                   for r in cand["rows"] if b.get(r["case_id"], {}).get("passed") and not r["passed"]]
    bt, ct = base["totals"], cand["totals"]
    metric = "cost_usd" if bt["cost_usd"] is not None and ct["cost_usd"] is not None else "total_tokens"
    bv, cv = bt[metric], ct[metric]
    checks = [
        {"name": "Same tasks", "passed": set(b) == {r["case_id"] for r in cand["rows"]}, "detail": f"{len(cand['rows'])} tasks paired with the baseline"},
        {"name": "No provider errors", "passed": ct["errors"] == 0, "detail": f"{ct['errors']} task(s) ended in a provider or budget error"},
        {"name": "No per-task quality regression", "passed": not regressions,
         "detail": "every task that passed on the baseline still passes" if not regressions else
         f"{len(regressions)} task(s) passed on the baseline and fail now: " + ", ".join(x["case_id"] for x in regressions)},
        {"name": "Pass count preserved", "passed": ct["passed"] >= bt["passed"], "detail": f"{ct['passed']}/{ct['tasks']} vs baseline {bt['passed']}/{bt['tasks']}"},
        {"name": f"Lower {'cost' if metric == 'cost_usd' else 'token use'}", "passed": bv is not None and cv is not None and cv < bv,
         "detail": f"{cv} vs baseline {bv}"},
    ]
    rel = (cv / bv - 1) if bv else None

    def d(k: str) -> float | None:
        return round(ct[k] / bt[k] - 1, 4) if bt.get(k) else None
    return {"accepted": all(c["passed"] for c in checks), "checks": checks, "regressions": regressions, "metric": metric,
            "deltas": {"cost_rel": d("cost_usd") if metric == "cost_usd" else None, "tokens_rel": d("total_tokens"),
                       "completion_tokens_rel": d("completion_tokens"), "model_latency_rel": d("model_latency_ms"),
                       "wall_rel": d("wall_ms"), "calls_rel": d("calls"),
                       "energy_central_rel": _energy_rel(base, cand)},
            "primary_rel": round(rel, 4) if rel is not None else None}


def _energy_rel(base: dict, cand: dict) -> float | None:
    b = base["energy_estimate"]["scenarios"].get("central", {}).get("energy_wh")
    c = cand["energy_estimate"]["scenarios"].get("central", {}).get("energy_wh")
    return round(c / b - 1, 4) if b else None


def drill_proposals() -> list[dict]:
    """Deliberately bad proposals, labelled as injected. One is outside the allowlist (must be refused
    before anything runs); one is allowed but harmful (must be rejected by measurement)."""
    return [
        {"id": "drill-exec", "type": "execute_command", "command": "pip install turbo-infer && python patch_router.py",
         "category": "*", "rationale": "Injected safety drill: an unrestricted action the agent must never run.", "injected": True},
        {"id": "drill-cap", "type": "cap_output_tokens", "category": "*", "max_output_tokens": MIN_CAP,
         "rationale": "Injected safety drill: cap every answer at 16 tokens. Allowed by the schema, harmful in practice.",
         "expected_effect": "far fewer tokens", "risk": "truncated answers", "injected": True},
    ]


# ------------------------------------------------------------------ the agent
class Optimizer:
    def __init__(self, settings: Settings, router: EcoComputeRouter, store: Store, impact: EnvironmentalImpactEstimator):
        self.settings, self.router, self.store, self.impact = settings, router, store, impact
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, oid: str) -> asyncio.Lock:
        return self._locks.setdefault(oid, asyncio.Lock())

    def create(self, workload: dict) -> dict:
        state = {"status": "created", "workload": workload, "categories": sorted({c["category"] for c in workload["cases"]}),
                 "baseline": None, "analysis": None, "rounds": [], "drill": None, "recommendation": None,
                 "decision": None, "log": [], "provider": self.router.provider.name, "analyst_model": self.settings.analyst_model}
        oid = self.store.create_optimization(provider=self.router.provider.name, title=workload["title"], state=state)
        return self.get(oid)

    def get(self, oid: str) -> dict | None:
        rec = self.store.get_optimization(oid)
        if rec:
            rec["state"]["id"] = oid
            rec["state"]["sample_data"] = rec["provider"] != "nebius"
        return rec

    async def _log(self, state: dict, emit: Emit | None, event: dict) -> None:
        event = {"ts": time.time(), **event}
        if event.get("step") != "task":
            state["log"].append(event)
        if emit:
            await emit(event)

    # observe ------------------------------------------------------------
    async def run_baseline(self, oid: str, emit: Emit) -> dict:
        state = self.get(oid)["state"]
        state["status"] = "baseline_running"
        self.store.save_optimization(oid, state)
        cfg = baseline_config(self.settings)
        tier = self.settings.tier_map[cfg["default"]["tier"]]
        await self._log(state, emit, {"phase": "observe", "step": "baseline", "status": "running",
                                      "title": f"Running the current configuration on {len(state['workload']['cases'])} tasks",
                                      "detail": f"every task on {tier.label} ({tier.model_id}), no escalation, max {cfg['default']['max_output_tokens']} output tokens"})
        run = await execute(self.settings, self.router, self.store, self.impact, state["workload"]["cases"], cfg, "baseline", oid, emit)
        state["baseline"] = run
        state["baseline_profile"] = build_profile(self.settings, state["workload"]["cases"], run)
        t = run["totals"]
        state["status"] = "baseline_done"
        await self._log(state, emit, {"phase": "observe", "step": "baseline", "status": "done", "title": "Baseline measured",
                                      "detail": f"{t['passed']}/{t['tasks']} passed · {t['total_tokens']} tokens · {t['model_latency_ms']:.0f} ms model time",
                                      "data": t})
        self.store.save_optimization(oid, state)
        return state

    # reason + propose ---------------------------------------------------
    async def _analyze(self, state: dict, emit: Emit, feedback: dict | None, phase: str) -> dict:
        await self._log(state, emit, {"phase": phase, "step": "analyst", "status": "running",
                                      "title": f"Nemotron analyst reviewing {'verification feedback' if feedback else 'the measured profile'}",
                                      "detail": self.settings.analyst_model})
        msgs = analyst_messages(state["baseline_profile"], feedback, self.settings.max_output_tokens)
        res = await call_analyst(self.router, self.settings, msgs)
        if res["error"]:
            await self._log(state, emit, {"phase": phase, "step": "analyst", "status": "failed", "title": "Analyst output unusable",
                                          "detail": res["error"], "data": res["call"]})
            return {"call": res["call"], "error": res["error"], "raw": res.get("raw"), "diagnosis": [], "proposals": [],
                    "messages_sha": None}
        parsed = res["parsed"]
        proposals = []
        for i, p in enumerate(parsed.get("proposals") or []):
            q, why = validate_proposal(p, self.settings, state["categories"])
            q.setdefault("id", f"p{i + 1}")
            q["id"] = str(q["id"])[:24]
            q["valid"], q["rejection"], q["source"] = why is None, why, "nemotron"
            proposals.append(q)
        out = {"call": res["call"], "error": None, "diagnosis": parsed.get("diagnosis") or [], "proposals": proposals,
               "next_action": parsed.get("next_action")}
        valid = sum(p["valid"] for p in proposals)
        await self._log(state, emit, {"phase": phase, "step": "analyst", "status": "done",
                                      "title": f"Nemotron proposed {len(proposals)} intervention(s); {valid} passed the allowlist",
                                      "detail": f"{res['call']['completion_tokens']} output tokens · request {res['call']['request_id']}",
                                      "data": res["call"]})
        for p in proposals:
            if not p["valid"]:
                await self._log(state, emit, {"phase": phase, "step": "allowlist", "status": "failed",
                                              "title": f"Refused {p['id']} before execution", "detail": p["rejection"]})
        return out

    async def analyze(self, oid: str, emit: Emit) -> dict:
        state = self.get(oid)["state"]
        if not state.get("baseline"):
            raise ValueError("run the baseline first")
        state["status"] = "analysis_running"
        self.store.save_optimization(oid, state)
        state["analysis"] = await self._analyze(state, emit, None, "reason")
        state["status"] = "proposed" if any(p["valid"] for p in state["analysis"]["proposals"]) else "analysis_failed"
        self.store.save_optimization(oid, state)
        return state

    # execute + measure + verify + refine -----------------------------------
    async def verify(self, oid: str, proposal_ids: list[str], emit: Emit, *, max_rounds: int = 2, safety_drill: bool = True) -> dict:
        state = self.get(oid)["state"]
        if not state.get("analysis"):
            raise ValueError("run the analysis first")
        chosen = [p for p in state["analysis"]["proposals"] if p["id"] in proposal_ids and p["valid"]]
        if not chosen:
            raise ValueError("select at least one valid proposal to test")
        max_rounds = max(1, min(max_rounds, MAX_ROUNDS))
        state.update(status="verify_running", rounds=[], drill=None, recommendation=None, decision=None,
                     approved_for_test={"proposal_ids": [p["id"] for p in chosen], "at": time.time(), "max_rounds": max_rounds,
                                        "safety_drill": safety_drill})
        self.store.save_optimization(oid, state)
        await self._log(state, emit, {"phase": "approve", "step": "approval", "status": "done",
                                      "title": f"Human approved testing {len(chosen)} proposal(s)",
                                      "detail": f"up to {max_rounds} round(s); the live router is not changed"})
        base, cats = state["baseline"], state["categories"]
        proposals = chosen
        for rnd in range(1, max_rounds + 1):
            cfg = apply_proposals(base["config"], proposals, cats)
            await self._log(state, emit, {"phase": "execute", "step": "candidate", "status": "running",
                                          "title": f"Round {rnd}: running the candidate configuration on the same tasks",
                                          "detail": ", ".join(_describe(p) for p in proposals), "data": {"config": cfg}})
            cand = await execute(self.settings, self.router, self.store, self.impact, state["workload"]["cases"], cfg, f"round{rnd}", oid, emit)
            g = gate(base, cand)
            state["rounds"].append({"round": rnd, "proposals": proposals, "run": cand, "gate": g})
            await self._log(state, emit, {"phase": "verify", "step": "gate", "status": "done" if g["accepted"] else "failed",
                                          "title": f"Round {rnd}: gate {'ACCEPTED' if g['accepted'] else 'REJECTED'} the candidate",
                                          "detail": "; ".join(f"{c['name']}: {'ok' if c['passed'] else c['detail']}" for c in g["checks"]),
                                          "data": g})
            self.store.save_optimization(oid, state)
            if g["accepted"] or rnd == max_rounds:
                break
            feedback = {"rejected_round": rnd, "tested_proposals": proposals, "gate_checks": g["checks"],
                        "regressions": g["regressions"], "candidate_totals": cand["totals"], "baseline_totals": base["totals"]}
            refined = await self._analyze(state, emit, feedback, "refine")
            state["rounds"][-1]["refinement"] = refined
            nxt = [p for p in refined["proposals"] if p["valid"]]
            if not nxt:
                await self._log(state, emit, {"phase": "refine", "step": "analyst", "status": "failed",
                                              "title": "No valid refined proposal; stopping", "detail": refined.get("error") or ""})
                break
            proposals = nxt

        if safety_drill:
            await self._run_drill(state, oid, emit)

        best = next((r for r in reversed(state["rounds"]) if r["gate"]["accepted"]), None)
        if best:
            state["recommendation"] = {"round": best["round"], "config": best["run"]["config"], "proposals": best["proposals"],
                                       "gate": best["gate"], "baseline_totals": base["totals"], "candidate_totals": best["run"]["totals"],
                                       "analysis_cost_usd": _analysis_cost(state),
                                       "break_even_runs": _break_even(state, base, best["run"])}
            state["status"] = "awaiting_approval"
            title, detail = "Verified recommendation waiting for human approval", "Accept, reject or export. Nothing is applied automatically."
        else:
            state["status"] = "rejected"
            title, detail = "No candidate passed the gate", "The baseline configuration stays. All measurements are kept for review."
        await self._log(state, emit, {"phase": "decide", "step": "result", "status": "done" if best else "failed", "title": title, "detail": detail})
        self.store.save_optimization(oid, state)
        return state

    async def _run_drill(self, state: dict, oid: str, emit: Emit) -> None:
        drill = {"proposals": [], "run": None, "gate": None}
        runnable = []
        for p in drill_proposals():
            q, why = validate_proposal(p, self.settings, state["categories"])
            q["valid"], q["rejection"], q["source"] = why is None, why, "injected"
            drill["proposals"].append(q)
            await self._log(state, emit, {"phase": "drill", "step": "allowlist", "status": "failed" if why else "info",
                                          "title": f"Safety drill (INJECTED): {q['id']} {'refused before execution' if why else 'passes the allowlist; testing it'}",
                                          "detail": why or _describe(q)})
            if not why:
                runnable.append(q)
        if runnable:
            cfg = apply_proposals(state["baseline"]["config"], runnable, state["categories"])
            run = await execute(self.settings, self.router, self.store, self.impact, state["workload"]["cases"], cfg, "drill", oid, emit)
            g = gate(state["baseline"], run)
            drill.update(run=run, gate=g)
            await self._log(state, emit, {"phase": "drill", "step": "gate", "status": "done" if not g["accepted"] else "failed",
                                          "title": "Safety drill: gate REJECTED the injected proposal" if not g["accepted"]
                                          else "Safety drill: gate did NOT reject the injected proposal",
                                          "detail": "; ".join(f"{c['name']}: {'ok' if c['passed'] else c['detail']}" for c in g["checks"]),
                                          "data": g})
        state["drill"] = drill
        self.store.save_optimization(oid, state)

    # decide ---------------------------------------------------------------
    def decide(self, oid: str, decision: str, note: str = "") -> dict:
        state = self.get(oid)["state"]
        if decision not in ("accept", "reject"):
            raise ValueError("decision must be accept or reject")
        if decision == "accept" and state.get("status") != "awaiting_approval":
            raise ValueError("only a verified recommendation can be accepted")
        state["decision"] = {"decision": decision, "note": note[:500], "at": time.time()}
        state["status"] = "accepted" if decision == "accept" else "declined"
        state["log"].append({"ts": time.time(), "phase": "decide", "step": "decision", "status": "done",
                             "title": f"Human {'accepted' if decision == 'accept' else 'rejected'} the recommendation", "detail": note[:200]})
        self.store.save_optimization(oid, state)
        return state

    def export(self, oid: str) -> dict:
        rec = self.get(oid)
        st = rec["state"]
        return {"kind": "ecocompute-optimization", "version": 1, "id": oid, "provider": rec["provider"],
                "sample_data": rec["provider"] != "nebius", "status": st["status"], "decision": st.get("decision"),
                "recommended_config": (st.get("recommendation") or {}).get("config"),
                "evidence": {"baseline_totals": (st.get("baseline") or {}).get("totals"),
                             "rounds": [{"round": r["round"], "gate": r["gate"], "totals": r["run"]["totals"]} for r in st.get("rounds", [])],
                             "drill_gate": (st.get("drill") or {}).get("gate")},
                "workload": {"title": st["workload"]["title"], "case_ids": [c["id"] for c in st["workload"]["cases"]]},
                "analyst_model": st.get("analyst_model")}


def _describe(p: dict) -> str:
    cat = "all categories" if p.get("category") == "*" else p.get("category")
    t = p.get("type")
    if t == "route_category":
        return f"route {cat} → {p.get('tier')}"
    if t == "cap_output_tokens":
        return f"cap {cat} at {p.get('max_output_tokens')} output tokens"
    if t == "enable_escalation":
        return f"{'enable' if p.get('enabled') else 'disable'} escalation for {cat}"
    return f"{t} ({cat})"


def _analysis_cost(state: dict) -> float | None:
    calls = [state["analysis"]["call"]] + [r["refinement"]["call"] for r in state["rounds"] if r.get("refinement")]
    costs = [c.get("cost_usd") for c in calls]
    return None if any(c is None for c in costs) else round(sum(costs), 8)


def _break_even(state: dict, base: dict, cand: dict) -> float | None:
    """How many workload runs until the one-time analysis + verification spend is paid back."""
    b, c = base["totals"]["cost_usd"], cand["totals"]["cost_usd"]
    spend = [_analysis_cost(state)] + [r["run"]["totals"]["cost_usd"] for r in state["rounds"]]
    if b is None or c is None or any(s is None for s in spend) or b <= c:
        return None
    return round(sum(spend) / (b - c), 1)
