import pytest

from app.providers.mock import MockProvider
from app.router.engine import EcoComputeRouter, WorkloadSpec

JSON_SPEC = dict(
    task="Return JSON with key result.", category="structured_json", output_format="json",
    checks=[{"type": "json_schema", "schema": {"type": "object", "required": ["result"]}}],
)


@pytest.mark.asyncio
async def test_invalid_json_triggers_escalation_and_passes(router, store):  # Acceptance tests 3 + 4
    events = []

    async def emit(e):
        events.append(e)

    out = await router.run(WorkloadSpec(**JSON_SPEC, forced_tier="small", allow_escalation=True), emit)
    assert out.status == "passed"
    assert out.final_tier == "medium"
    assert out.totals["escalations"] == 1 and out.totals["calls"] == 2
    steps = [(e["step"], e["status"]) for e in events]
    assert ("evaluate", "failed") in steps and ("escalate", "info") in steps and ("evaluate", "done") in steps
    # Machine-readable trace persisted
    w = store.get_workload(out.workload_id)
    assert w["trace"] and w["trace"][-1]["step"] == "final"
    assert [a["tier"] for a in w["attempts"]] == ["small", "medium"]
    assert w["attempts"][0]["passed"] == 0 and w["attempts"][1]["passed"] == 1


@pytest.mark.asyncio
async def test_escalation_disabled_reports_failure(router):
    out = await router.run(WorkloadSpec(**JSON_SPEC, forced_tier="small", allow_escalation=False))
    assert out.status == "failed" and out.totals["calls"] == 1


@pytest.mark.asyncio
async def test_repair_attempt_is_bounded(router):
    out = await router.run(WorkloadSpec(**JSON_SPEC, forced_tier="small", allow_escalation=True, repair_attempts=1))
    # Mock small model stays broken: 1 original + 1 repair on small, then escalation to medium.
    assert out.totals["repairs"] == 1 and out.totals["calls"] == 3 and out.status == "passed"


@pytest.mark.asyncio
async def test_persistence_records_tokens_latency_cost(router, store):  # Acceptance test 5
    out = await router.run(WorkloadSpec(task="Classify: great. Reply positive or negative.", category="classification",
                                        checks=[{"type": "regex", "pattern": "mock"}]))
    w = store.get_workload(out.workload_id)
    assert w["status"] == "passed" and w["created_at"] > 0
    assert w["prompt_tokens"] > 0 and w["completion_tokens"] > 0 and w["latency_ms"] > 0
    assert w["cost_usd"] is not None and w["cost_usd"] > 0
    a = w["attempts"][0]
    assert a["model"] and a["eval_method"] == "regex" and a["latency_ms"] > 0


@pytest.mark.asyncio
async def test_unverified_when_no_checks(router):
    out = await router.run(WorkloadSpec(task="Write a haiku about rain."))
    assert out.status == "unverified"


@pytest.mark.asyncio
async def test_judge_is_labelled_as_estimate_and_costed(router, store):
    out = await router.run(WorkloadSpec(task="Write a friendly greeting.", use_judge=True))
    assert out.status == "passed"
    w = store.get_workload(out.workload_id)
    assert w["eval_method"] == "model_judge_estimate"
    assert any(a["role"] == "judge" for a in w["attempts"])
    assert w["overhead_cost_usd"] > 0


@pytest.mark.asyncio
async def test_learning_updates_evidence(router):
    for _ in range(3):
        await router.run(WorkloadSpec(**JSON_SPEC, forced_tier="small"))
    ev = router.evidence()
    assert ev[("structured_json", "small")]["n"] == 3 and ev[("structured_json", "small")]["passes"] == 0
    # After evidence of failures, the free (forced-less) router no longer starts on small for this category.
    out = await router.run(WorkloadSpec(**JSON_SPEC, quality_threshold=0.85))
    assert out.decision["start_tier"] != "small"


class FailingProvider(MockProvider):
    async def chat(self, model, messages, **kw):
        from app.providers.base import ChatResult
        return ChatResult(ok=False, model=model, error="HTTP 503: upstream unavailable", error_type="http", latency_ms=5)


@pytest.mark.asyncio
async def test_provider_errors_are_honest_not_fabricated(settings, store):
    prov = FailingProvider({t.model_id: t.rank for t in settings.tiers})
    r = EcoComputeRouter(settings, prov, store)
    out = await r.run(WorkloadSpec(**JSON_SPEC))
    assert out.status == "error" and out.final_output == ""


class FakeNebius(MockProvider):
    name = "nebius"  # exercises budget guardrails, which only apply to paid providers


@pytest.mark.asyncio
async def test_daily_budget_guardrail_blocks_calls(settings, store):
    import dataclasses
    tight = dataclasses.replace(settings, daily_budget_usd=0.0)
    r = EcoComputeRouter(tight, FakeNebius({t.model_id: t.rank for t in settings.tiers}), store)
    out = await r.run(WorkloadSpec(**JSON_SPEC))
    assert out.status == "budget_blocked" and out.totals["calls"] == 0


@pytest.mark.asyncio
async def test_workload_budget_stops_escalation(settings, store):
    import dataclasses
    tight = dataclasses.replace(settings, max_workload_cost_usd=1e-9)
    r = EcoComputeRouter(tight, FakeNebius({t.model_id: t.rank for t in settings.tiers}), store)
    out = await r.run(WorkloadSpec(**JSON_SPEC, forced_tier="small", allow_escalation=True))
    assert out.totals["calls"] == 1 and any(e["step"] == "guardrail" for e in out.trace)
