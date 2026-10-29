"""EcoCompute Challenge: failure handling tested with deterministic fixtures.

The fixture provider returns scripted answers per model. It exists only in
tests; the live challenge always uses the configured provider.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.challenge import SCENARIO_MAP, compare, run_challenge
from app.providers.base import ChatResult
from app.router.engine import EcoComputeRouter

ROUTINE_OK = json.dumps({"ticket_1": "billing", "ticket_2": "technical", "ticket_3": "shipping"})
ROUTINE_BAD = json.dumps({"ticket_1": "billing", "ticket_2": "account", "ticket_3": "shipping"})
DEMANDING_OK = json.dumps({"shipments": [
    {"id": "SHP-4410", "origin": "MIA", "destination": "ATL", "departure": "2026-11-03T18:45", "status": "delayed", "delay_minutes": 90, "hazmat": True},
    {"id": "SHP-4411", "origin": "MCO", "destination": "EWR", "departure": "2026-11-04T07:10", "status": "scheduled", "delay_minutes": None, "hazmat": False},
    {"id": "SHP-4412", "origin": "PBI", "destination": "JFK", "departure": "2026-11-04T12:00", "status": "cancelled", "delay_minutes": None, "hazmat": True},
    {"id": "SHP-4413", "origin": "TPA", "destination": "ORD", "departure": "2026-11-05T21:05", "status": "delayed", "delay_minutes": 20, "hazmat": False},
]})
DEMANDING_BAD = DEMANDING_OK.replace('"2026-11-03T18:45"', '"2026-11-03T06:45"')  # 12h clock misread


class FixtureProvider:
    """Scripted answers per tier rank; tokens scale with rank so cost ordering is realistic."""
    name = "fixture"

    def __init__(self, tier_rank: dict[str, int], answers: dict[int, str]):
        self._rank, self._answers, self.calls = tier_rank, answers, []

    async def aclose(self):
        return None

    async def list_models(self):
        return [{"id": m} for m in self._rank]

    async def chat(self, model, messages, *, max_tokens, temperature, response_format=None):
        rank = self._rank[model]
        self.calls.append(model)
        return ChatResult(ok=True, model=model, content=self._answers[rank], prompt_tokens=200, completion_tokens=100 + 200 * rank,
                          latency_ms=500.0 * (1 + rank), finish_reason="stop", provider="fixture", request_id=f"fx-{len(self.calls)}")


def _router(settings, store, answers):
    prov = FixtureProvider({t.model_id: t.rank for t in settings.tiers}, answers)
    return EcoComputeRouter(settings, prov, store), prov


async def test_first_attempt_success_is_cheaper_than_baseline(settings, store):
    router, prov = _router(settings, store, {0: ROUTINE_OK, 1: ROUTINE_OK, 2: ROUTINE_OK})
    c = await run_challenge(settings, router, store, "routine")
    cmp = c["comparison"]
    eco, base = cmp["lanes"]["ecocompute"], cmp["lanes"]["baseline"]
    assert c["status"] == "completed" and cmp["sample_data"] is True
    assert eco["outcome"] == "first_attempt_pass" and eco["initial_tier"] == "small" and eco["calls"] == 1
    assert eco["started_below_baseline"] is True
    assert base["final_tier"] == "large" and base["passed"] and base["calls"] == 1
    assert cmp["improved"] is True and cmp["deltas"]["cost_rel"] < 0 and "Improved" in cmp["verdict"]
    assert eco["overhead"]["paid_overhead_calls"] == 0 and eco["overhead"]["overhead_cost_usd"] == 0
    assert eco["call_log"][0]["request_id"].startswith("fx-") and eco["call_log"][0]["provider"] == "fixture"


async def test_validator_failure_triggers_escalation_and_same_requirement(settings, store):
    router, prov = _router(settings, store, {0: DEMANDING_BAD, 1: DEMANDING_OK, 2: DEMANDING_OK})
    c = await run_challenge(settings, router, store, "demanding")
    eco = c["comparison"]["lanes"]["ecocompute"]
    assert eco["outcome"] == "escalated_then_passed"
    assert [e["passed"] for e in eco["evaluations"]] == [False, True]
    assert len({e["method"] for e in eco["evaluations"]}) == 1  # same requirement both times
    assert "shipments.0.departure" in eco["evaluations"][0]["detail"]
    assert [x["tier"] for x in eco["call_log"]] == ["small", "medium"]
    assert "rejected" in c["comparison"]["what_happened"]


async def test_escalation_can_cost_more_and_is_reported_as_no_improvement(settings, store):
    router, _ = _router(settings, store, {0: ROUTINE_BAD, 1: ROUTINE_BAD, 2: ROUTINE_OK})
    cmp = (await run_challenge(settings, router, store, "routine"))["comparison"]
    assert cmp["lanes"]["ecocompute"]["escalations"] == 2
    assert cmp["improved"] is False and cmp["deltas"]["cost_rel"] > 0
    assert cmp["verdict"].startswith("No improvement") and "escalated" in cmp["verdict"]


async def test_small_success_on_hard_scenario_is_not_hidden(settings, store):
    router, _ = _router(settings, store, {0: DEMANDING_OK, 1: DEMANDING_OK, 2: DEMANDING_OK})
    cmp = (await run_challenge(settings, router, store, "demanding"))["comparison"]
    assert cmp["lanes"]["ecocompute"]["outcome"] == "first_attempt_pass"
    assert "never forced" in cmp["what_happened"]


def test_tradeoff_verdicts():
    lane = lambda passed, cost, tok=100, esc=0: {"passed": passed, "total_cost_usd": cost, "total_tokens": tok, "wall_ms": 1000, "model_latency_ms": 900, "escalations": esc}
    assert compare(lane(False, 0.001), lane(True, 0.01))["verdict"].startswith("Tradeoff")
    assert compare(lane(True, 0.02), lane(False, 0.01))["verdict"].startswith("Better quality")
    assert compare(lane(False, 0.001), lane(False, 0.01))["improved"] is False
    assert "tokens" in compare(lane(True, None, 50), lane(True, None, 100))["verdict"]


def test_challenge_stream_endpoint(settings, store):
    router, _ = _router(settings, store, {0: DEMANDING_BAD, 1: DEMANDING_OK, 2: DEMANDING_OK})
    main.init_state(settings, router.provider)
    with TestClient(main.app) as c:
        assert {s["id"] for s in c.get("/api/challenge/scenarios").json()["scenarios"]} == set(SCENARIO_MAP)
        with c.stream("POST", "/api/challenge/demanding/stream") as r:
            body = r.read().decode()
        events = [json.loads(ch.split("data: ", 1)[1]) for ch in body.strip().split("\n\n") if ch.startswith("event: event")]
        assert {e["lane"] for e in events if e.get("step") != "challenge"} == {"ecocompute", "baseline"}
        done = json.loads([ch for ch in body.split("\n\n") if ch.startswith("event: done")][0].split("data: ", 1)[1])
        assert done["comparison"]["lanes"]["ecocompute"]["outcome"] == "escalated_then_passed"
        assert c.get(f"/api/challenges/{done['id']}").json()["status"] == "completed"
        assert c.get("/api/challenges").json()["items"][0]["id"] == done["id"]
        assert c.post("/api/challenge/nope/stream").status_code == 404


@pytest.mark.parametrize("sid", list(SCENARIO_MAP))
def test_scenario_answers_pass_their_own_validators(sid):
    from app.evaluation.validators import evaluate
    ok = {"routine": ROUTINE_OK, "demanding": DEMANDING_OK}[sid]
    assert evaluate(ok, SCENARIO_MAP[sid]["checks"]).passed
