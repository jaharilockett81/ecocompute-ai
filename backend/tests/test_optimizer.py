"""EcoCompute Optimizer: the observe → reason → propose → approve → execute → verify → refine → decide loop.

A fixture provider answers each task from its checks and scripts the analyst's
JSON, so every branch (allowlist refusal, gate rejection, bounded refinement,
acceptance, safety drill, human decision) is tested without the network.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.optimizer import (ANALYST_MARK, Optimizer, apply_proposals, baseline_config, gate, preset_workloads,
                           validate_proposal, validate_upload)
from app.providers.base import ChatResult
from app.providers.mock import reference_answer
from app.router.engine import EcoComputeRouter
from app.sustainability.estimator import EnvironmentalImpactEstimator

ROUND1 = {"diagnosis": [{"finding": "Every task runs on Ultra", "evidence": "8/8 on large", "categories": ["classification", "extraction"]}],
          "proposals": [{"id": "a", "type": "route_category", "category": "*", "tier": "small", "rationale": "cheap"},
                        {"id": "x", "type": "run_shell", "command": "rm -rf /", "rationale": "speed"}],
          "next_action": "test"}
ROUND2 = {"diagnosis": [{"finding": "Small fails extraction", "evidence": "4 regressions"}],
          "proposals": [{"id": "b", "type": "route_category", "category": "classification", "tier": "small"},
                        {"id": "c", "type": "cap_output_tokens", "category": "classification", "max_output_tokens": 512}]}


class TaskFixtureProvider:
    """Correct answers from each case's checks; the small tier gets extraction wrong. Honours max_tokens."""
    name = "fixture"

    def __init__(self, settings, cases, analyst_script, reject_response_format=False):
        self._rank = {t.model_id: t.rank for t in settings.tiers}
        self._cases = cases
        self._script = list(analyst_script)
        self._reject_rf = reject_response_format
        self.analyst_calls = []

    async def aclose(self):
        return None

    async def list_models(self):
        return [{"id": m} for m in self._rank]

    async def chat(self, model, messages, *, max_tokens, temperature, response_format=None):
        prompt = "\n".join(m["content"] for m in messages)
        rank = self._rank[model]
        if ANALYST_MARK in prompt:
            if response_format and self._reject_rf:
                return ChatResult(ok=False, model=model, provider="fixture", error="response_format unsupported", error_type="bad_request")
            self.analyst_calls.append({"prompt": prompt, "response_format": response_format})
            body = self._script.pop(0)
            return ChatResult(ok=True, model=model, content=body if isinstance(body, str) else json.dumps(body), prompt_tokens=900,
                              completion_tokens=400, latency_ms=2000, finish_reason="stop", provider="fixture", request_id=f"an-{len(self.analyst_calls)}")
        case = next(c for c in self._cases if c["task"] in prompt)
        content = reference_answer(case)
        if rank == 0 and case["category"] == "extraction":
            content = "{}"
        completion = 40 + 300 * rank
        finish = "stop"
        if completion > max_tokens:
            content, completion, finish = "", max_tokens, "length"
        return ChatResult(ok=True, model=model, content=content, prompt_tokens=150, completion_tokens=completion,
                          latency_ms=300.0 * (1 + rank), finish_reason=finish, provider="fixture", request_id=f"t-{case['id']}-{rank}")


def _setup(settings, store, script, **kw):
    wl = next(w for w in preset_workloads() if w["id"] == "support-ops")
    prov = TaskFixtureProvider(settings, wl["cases"], script, **kw)
    router = EcoComputeRouter(settings, prov, store)
    impact = EnvironmentalImpactEstimator({t.key: t.active_params_b for t in settings.tiers})
    return Optimizer(settings, router, store, impact), wl, prov


async def _noop(ev):
    return None


async def test_full_loop_rejects_then_refines_then_waits_for_human(settings, store):
    opt, wl, prov = _setup(settings, store, [ROUND1, ROUND2])
    oid = opt.create(wl)["state"]["id"]
    events = []

    async def emit(ev):
        events.append(ev)

    st = await opt.run_baseline(oid, emit)
    assert st["baseline"]["totals"]["passed"] == 8 and st["baseline"]["totals"]["tasks"] == 8
    assert st["baseline_profile"]["categories"]["extraction"]["final_tiers"] == {"large": 4}

    st = await opt.analyze(oid, emit)
    props = {p["id"]: p for p in st["analysis"]["proposals"]}
    assert props["a"]["valid"] and not props["x"]["valid"] and "not an allowed intervention" in props["x"]["rejection"]
    assert props["x"]["requested"]["command"] == "rm -rf /"  # recorded, never executed
    assert prov.analyst_calls[0]["response_format"] == {"type": "json_object"}
    assert "MEASURED PROFILE" in prov.analyst_calls[0]["prompt"]
    assert st["status"] == "proposed"

    with pytest.raises(ValueError):
        await opt.verify(oid, ["x"], emit)  # refused proposals cannot be tested

    st = await opt.verify(oid, ["a"], emit, max_rounds=2, safety_drill=True)
    r1, r2 = st["rounds"]
    assert not r1["gate"]["accepted"] and {x["category"] for x in r1["gate"]["regressions"]} == {"extraction"}
    assert "REJECTED BY THE VERIFICATION GATE" in prov.analyst_calls[1]["prompt"]  # measured feedback went back to Nemotron
    assert r2["gate"]["accepted"] and r2["gate"]["deltas"]["cost_rel"] < 0
    assert r2["run"]["config"]["per_category"] == {"classification": {"tier": "small", "max_output_tokens": 512}}
    assert all(c["passed"] for c in r2["gate"]["checks"])

    drill = st["drill"]
    by_id = {p["id"]: p for p in drill["proposals"]}
    assert by_id["drill-exec"]["valid"] is False and by_id["drill-exec"]["injected"] is True
    assert by_id["drill-cap"]["valid"] is True and drill["gate"]["accepted"] is False
    assert drill["run"]["totals"]["passed"] == 0  # 16-token cap truncates every answer

    rec = st["recommendation"]
    assert st["status"] == "awaiting_approval" and rec["round"] == 2
    assert rec["analysis_cost_usd"] > 0 and rec["break_even_runs"] > 0
    assert any(e.get("step") == "approval" for e in st["log"])
    assert any(e.get("step") == "task" for e in events)
    assert st["baseline"]["measurement_notes"]["gpu_utilization"].startswith("not observable")

    st = opt.decide(oid, "accept", "ship it")
    assert st["status"] == "accepted" and st["decision"]["decision"] == "accept"
    exp = opt.export(oid)
    assert exp["recommended_config"]["per_category"]["classification"]["tier"] == "small"
    assert exp["evidence"]["drill_gate"]["accepted"] is False and exp["sample_data"] is True

    # Optimizer traffic and analyst calls never pollute routing evidence for other workloads... but tasks do count as
    # ordinary primary attempts; check the analyst made no attempt rows.
    roles = {a["role"] for w in store.workloads_for_run(oid) for a in store.get_workload(w["id"])["attempts"]}
    assert roles == {"primary"}


async def test_no_candidate_passes_keeps_baseline(settings, store):
    bad = {"diagnosis": [], "proposals": [{"id": "a", "type": "route_category", "category": "*", "tier": "small"}]}
    opt, wl, _ = _setup(settings, store, [bad, bad])
    oid = opt.create(wl)["state"]["id"]
    await opt.run_baseline(oid, _noop)
    await opt.analyze(oid, _noop)
    st = await opt.verify(oid, ["a"], _noop, max_rounds=2, safety_drill=False)
    assert st["status"] == "rejected" and st["recommendation"] is None and len(st["rounds"]) == 2
    assert st["drill"] is None
    with pytest.raises(ValueError):
        opt.decide(oid, "accept")
    assert opt.decide(oid, "reject")["status"] == "declined"


async def test_unusable_analyst_output_is_reported_not_guessed(settings, store):
    opt, wl, _ = _setup(settings, store, ["I think you should use a smaller model."])
    oid = opt.create(wl)["state"]["id"]
    await opt.run_baseline(oid, _noop)
    st = await opt.analyze(oid, _noop)
    assert st["status"] == "analysis_failed" and "not valid JSON" in st["analysis"]["error"]
    assert st["analysis"]["proposals"] == []


async def test_falls_back_to_plain_json_when_response_format_is_rejected(settings, store):
    opt, wl, prov = _setup(settings, store, [ROUND2], reject_response_format=True)
    oid = opt.create(wl)["state"]["id"]
    await opt.run_baseline(oid, _noop)
    st = await opt.analyze(oid, _noop)
    assert st["status"] == "proposed" and st["analysis"]["call"]["structured_output"] is False
    assert prov.analyst_calls[0]["response_format"] is None


def test_proposal_allowlist(settings):
    cats = ["classification"]
    ok = lambda p: validate_proposal(p, settings, cats)[1]
    assert ok({"type": "route_category", "category": "classification", "tier": "small"}) is None
    assert "unknown tier" in ok({"type": "route_category", "category": "classification", "tier": "gpt-9"})
    assert "not in this workload" in ok({"type": "route_category", "category": "coding", "tier": "small"})
    assert "between" in ok({"type": "cap_output_tokens", "category": "*", "max_output_tokens": 4})
    assert "between" in ok({"type": "cap_output_tokens", "category": "*", "max_output_tokens": "lots"})
    assert "true or false" in ok({"type": "enable_escalation", "category": "*", "enabled": "yes"})
    assert "not an allowed" in ok({"type": "edit_file", "path": "/etc/passwd"})


def test_gate_is_strict_per_task(settings):
    def run(passes, cost):
        rows = [{"case_id": str(i), "category": "c", "passed": p, "status": "passed" if p else "failed", "eval_detail": "",
                 "final_tier": "small", "finish_reason": "stop"} for i, p in enumerate(passes)]
        return {"rows": rows, "energy_estimate": {"scenarios": {"central": {"energy_wh": cost}}},
                "totals": {"tasks": len(passes), "passed": sum(passes), "errors": 0, "cost_usd": cost, "total_tokens": 100,
                           "completion_tokens": 50, "model_latency_ms": 10, "wall_ms": 10, "calls": len(passes)}}
    base = run([True, False, True], 1.0)
    # Same pass count but a different task now fails: rejected.
    g = gate(base, run([False, True, True], 0.5))
    assert not g["accepted"] and [r["case_id"] for r in g["regressions"]] == ["0"]
    assert not gate(base, run([True, False, True], 1.0))["accepted"]  # no saving
    assert gate(base, run([True, True, True], 0.5))["accepted"]


def test_apply_proposals_and_upload_validation(settings):
    cfg = apply_proposals(baseline_config(settings), [{"type": "route_category", "category": "*", "tier": "small"},
                                                      {"type": "enable_escalation", "category": "b", "enabled": True}], ["a", "b"])
    assert cfg["per_category"] == {"a": {"tier": "small"}, "b": {"tier": "small", "escalation": True}}
    good = [{"task": "Say hi", "checks": [{"type": "contains_all", "terms": ["hi"]}]}]
    assert validate_upload(good, settings)[0]["category"] == "general"
    for bad, msg in [([], "expected"), ([{"task": "x"}], "deterministic check"),
                     ([{"task": "x", "checks": [{"type": "llm_vibes"}]}], "unknown check"),
                     ([{"task": "x", "category": "poetry", "checks": good[0]["checks"]}], "category")]:
        with pytest.raises(ValueError, match=msg):
            validate_upload(bad, settings)


def _events(body: str, kind="event"):
    return [json.loads(ch.split("data: ", 1)[1]) for ch in body.strip().split("\n\n") if ch.startswith(f"event: {kind}")]


def test_optimizer_api_end_to_end(settings, store):
    wl = next(w for w in preset_workloads() if w["id"] == "support-ops")
    prov = TaskFixtureProvider(settings, wl["cases"], [ROUND2])
    main.init_state(settings, prov)
    with TestClient(main.app) as c:
        assert {w["id"] for w in c.get("/api/optimize/workloads").json()["workloads"]} == {"support-ops", "data-pipeline", "mixed-agent"}
        assert c.post("/api/optimize/sessions", json={"preset": "nope"}).status_code == 404
        assert c.post("/api/optimize/sessions", json={"cases": [{"task": "x"}]}).status_code == 422
        oid = c.post("/api/optimize/sessions", json={"preset": "support-ops"}).json()["id"]
        assert c.post(f"/api/optimize/sessions/{oid}/analyze").status_code == 409
        with c.stream("POST", f"/api/optimize/sessions/{oid}/baseline") as r:
            body = r.read().decode()
        assert len([e for e in _events(body) if e["step"] == "task"]) == 8
        with c.stream("POST", f"/api/optimize/sessions/{oid}/analyze") as r:
            st = _events(r.read().decode(), "done")[0]
        assert st["status"] == "proposed"
        with c.stream("POST", f"/api/optimize/sessions/{oid}/verify", json={"proposal_ids": ["b", "c"], "max_rounds": 1}) as r:
            st = _events(r.read().decode(), "done")[0]
        assert st["status"] == "awaiting_approval" and st["drill"]["gate"]["accepted"] is False
        assert c.post(f"/api/optimize/sessions/{oid}/decision", json={"decision": "accept"}).json()["status"] == "accepted"
        assert c.get(f"/api/optimize/sessions/{oid}/export").json()["recommended_config"]
        assert c.get("/api/optimize/sessions").json()["items"][0]["summary"]["drill_rejected"] is True
        bundle = c.get(f"/api/bundles/optimization/{oid}").json()
        assert bundle["record"]["state"]["status"] == "accepted" and len(bundle["workloads"]) == 8 * 3


def test_optimization_bundle_round_trip(settings, store, tmp_path):
    from app.persistence.bundles import import_bundle
    from app.persistence.store import Store
    oid = store.create_optimization(provider="nebius", title="t", state={"status": "accepted", "workload": {"cases": []}})
    from app.persistence.bundles import export_bundle
    b = json.loads(json.dumps(export_bundle(store, "optimization", oid), default=str))
    fresh = Store(str(tmp_path / "f.db"))
    assert import_bundle(fresh, b) is True and fresh.get_optimization(oid)["state"]["status"] == "accepted"
