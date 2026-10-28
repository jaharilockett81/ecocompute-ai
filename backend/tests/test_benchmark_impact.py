import pytest

from app.benchmark.metrics import compare, condition_summary, wilson
from app.benchmark.runner import BenchmarkRunner, load_dataset
from app.sustainability.estimator import EnvironmentalImpactEstimator


def test_dataset_is_balanced_and_checkable():
    ds = load_dataset()
    cases = ds["cases"]
    assert len(cases) == 49 and len({c["id"] for c in cases}) == 49
    cats = {c["category"] for c in cases}
    assert len(cats) == 7
    for cat in cats:
        group = [c for c in cases if c["category"] == cat]
        assert len(group) == 7 and sum(c["split"] == "calib" for c in group) == 2
    assert all(c["checks"] for c in cases)


@pytest.mark.asyncio
async def test_benchmark_runs_identical_tasks_and_compares(settings, router, store):  # Acceptance test 6
    br = BenchmarkRunner(settings, router, store)
    run = br.create(conditions=["fixed:large", "adaptive", "fixed:small"], split="test", categories=["structured_json", "classification"], limit=6)
    await br.wait(run["id"])
    done = store.get_run(run["id"])
    assert done["status"] == "completed" and done["progress_done"] == 18
    s = done["summary"]
    assert s["sample_data"] is True and s["baseline"] == "fixed:large"
    assert set(s["conditions"]) == {"fixed:large", "adaptive", "fixed:small"}
    cmp = s["comparisons"]["adaptive"]
    assert cmp["paired_tasks"] == 6 and cmp["cost_rel_change"] is not None
    # identical task text across conditions
    rows = store.workloads_for_run(run["id"])
    by_case = {}
    for r in rows:
        by_case.setdefault(r["case_id"], set()).add(r["task_text"])
    assert all(len(v) == 1 for v in by_case.values())


def test_call_cap_refuses_expensive_runs(settings, router, store):
    br = BenchmarkRunner(settings, router, store)
    with pytest.raises(ValueError, match="exceeds the call cap"):
        br.create(conditions=["adaptive", "fixed:large"], split="all", repeats=3, max_calls=10)
    with pytest.raises(ValueError, match="unknown condition"):
        br.create(conditions=["fixed:huge"])


@pytest.mark.asyncio
async def test_cancel_stops_run(settings, router, store):
    br = BenchmarkRunner(settings, router, store)
    run = br.create(conditions=["fixed:large"], split="all")
    br.cancel(run["id"])
    await br.wait(run["id"])
    assert store.get_run(run["id"])["status"] == "cancelled"


@pytest.mark.asyncio
async def test_warm_start_uses_only_calibration_evidence(settings, router, store):
    br = BenchmarkRunner(settings, router, store)
    calib = br.create(conditions=["fixed:small"], split="calib", categories=["structured_json"])
    await br.wait(calib["id"])
    ev = store.calibration_evidence("mock", ["json-01", "json-02"])
    assert ev[("structured_json", "small")]["n"] == 2
    assert store.calibration_evidence("mock", ["json-03"]) == {}


def test_metrics_helpers():
    assert wilson(0, 0) is None
    lo, hi = wilson(8, 10)
    assert lo < 0.8 < hi
    rows_b = [{"case_id": str(i), "status": "passed", "cost_usd": 0.01, "latency_ms": 1000, "prompt_tokens": 100, "completion_tokens": 100, "calls": 1, "usage_complete": True} for i in range(10)]
    rows_a = [dict(r, cost_usd=0.004, latency_ms=600) for r in rows_b]
    assert condition_summary(rows_a)["success_rate"] == 1.0
    c = compare(rows_a, rows_b)
    assert c["cost_rel_change"] == -0.6 and c["latency_mean_rel_change"] == -0.4


def test_impact_estimates_are_scenarios_with_labels():  # Acceptance test 7
    est = EnvironmentalImpactEstimator({"small": 3.0, "large": 55.0, "unknown": None})
    small = est.estimate_call("small", 300, 600)
    large = est.estimate_call("large", 300, 600)
    lo, mid, hi = (r.energy_wh for r in small)
    assert lo < mid < hi
    assert large[1].energy_wh / small[1].energy_wh == pytest.approx(55 / 3)
    agg = est.estimate_attempts([
        {"ok": 1, "tier": "small", "prompt_tokens": 300, "completion_tokens": 600},
        {"ok": 1, "tier": "unknown", "prompt_tokens": 300, "completion_tokens": 600},
        {"ok": 1, "tier": "small", "prompt_tokens": None, "completion_tokens": None},
    ])
    assert agg["calls_estimated"] == 1 and agg["calls_not_estimable"] == 2
    assert agg["category"].startswith("B")
    m = est.methodology()
    assert m["not_observable"] and m["sources"] and "latency" in m["why_not_latency"]
