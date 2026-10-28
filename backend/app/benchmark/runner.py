"""Benchmark runner: identical tasks under several routing conditions.

Conditions
  fixed:<tier>    always use one tier, no escalation (fixed:<baseline_tier> is the baseline)
  adaptive        EcoCompute routing, cold start (heuristic prior only, no learned evidence)
  adaptive_warm   EcoCompute routing warm-started ONLY from evidence on calibration-split cases

Guardrails: worst-case call count is computed before starting and refused above
the configured cap; the run stops if the cap or the daily budget is hit; runs
are cancellable. For every case, conditions are executed back to back so time-
of-day load affects all conditions similarly.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from app.benchmark.metrics import by_category, compare, condition_summary
from app.core.config import ROOT, Settings
from app.core.logging import get_logger
from app.persistence.store import Store
from app.router.engine import EcoComputeRouter, WorkloadSpec

log = get_logger("ecocompute.benchmark")


class _Stop(Exception):
    """Internal: ends a run early (cancel, cap, budget)."""

DATASET_PATH = ROOT / "benchmarks" / "datasets" / "ecobench-v1.json"
RESULTS_DIR = ROOT / "benchmarks" / "results"


def results_dir() -> Path:
    return Path(os.environ.get("ECOCOMPUTE_RESULTS_DIR") or RESULTS_DIR)


def load_dataset(path: Path = DATASET_PATH) -> dict:
    return json.loads(path.read_text())


def select_cases(dataset: dict, split: str = "test", categories: list[str] | None = None, case_ids: list[str] | None = None, limit: int | None = None) -> list[dict]:
    cases = dataset["cases"]
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c["id"] in wanted]
    else:
        if split != "all":
            cases = [c for c in cases if c["split"] == split]
        if categories:
            cases = [c for c in cases if c["category"] in set(categories)]
    return cases[:limit] if limit else cases


class BenchmarkRunner:
    def __init__(self, settings: Settings, router: EcoComputeRouter, store: Store):
        self.settings = settings
        self.router = router
        self.store = store
        self._cancel: dict[str, asyncio.Event] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def max_calls_for(self, conditions: list[str], n_cases: int, repeats: int) -> int:
        per_case = 0
        for c in conditions:
            per_case += 1 if c.startswith("fixed:") else len(self.settings.tiers)
        return per_case * n_cases * repeats

    def validate_conditions(self, conditions: list[str]) -> list[str]:
        valid = {f"fixed:{t.key}" for t in self.settings.tiers} | {"adaptive", "adaptive_warm"}
        bad = [c for c in conditions if c not in valid]
        if bad:
            raise ValueError(f"unknown condition(s) {bad}; valid: {sorted(valid)}")
        return list(dict.fromkeys(conditions))

    def create(self, *, conditions: list[str], split: str = "test", categories: list[str] | None = None,
               case_ids: list[str] | None = None, limit: int | None = None, repeats: int = 1, max_calls: int | None = None) -> dict:
        conditions = self.validate_conditions(conditions)
        dataset = load_dataset()
        cases = select_cases(dataset, split, categories, case_ids, limit)
        if not cases:
            raise ValueError("no benchmark cases match the selection")
        repeats = max(1, min(repeats, 5))
        cap = min(max_calls or self.settings.benchmark_max_calls, self.settings.benchmark_max_calls)
        worst = self.max_calls_for(conditions, len(cases), repeats)
        if worst > cap:
            raise ValueError(f"worst-case {worst} calls exceeds the call cap of {cap}; select fewer cases/conditions or raise ECOCOMPUTE_BENCHMARK_MAX_CALLS")
        if self.router.provider.name == "nebius" and any(r["status"] in ("queued", "running") for r in self.store.list_runs(5)):
            raise ValueError("another benchmark is already running")

        rid = self.store.create_run(
            status="queued", provider=self.router.provider.name, dataset_version=dataset["version"],
            conditions_json=conditions, case_ids_json=[c["id"] for c in cases], max_calls=cap,
            progress_total=len(cases) * len(conditions) * repeats,
            config_json={"split": split, "categories": categories, "repeats": repeats, "worst_case_calls": worst,
                         "baseline": f"fixed:{self.settings.baseline_tier}", "temperature": self.settings.temperature,
                         "max_output_tokens": self.settings.max_output_tokens,
                         "tiers": [{"key": t.key, "model_id": t.model_id} for t in self.settings.tiers]},
        )
        self._cancel[rid] = asyncio.Event()
        self._tasks[rid] = asyncio.create_task(self._run(rid, cases, conditions, repeats, cap, dataset))
        return self.store.get_run(rid)

    def cancel(self, rid: str) -> bool:
        ev = self._cancel.get(rid)
        if ev and not ev.is_set():
            ev.set()
            return True
        return False

    async def wait(self, rid: str) -> None:
        task = self._tasks.get(rid)
        if task:
            await task

    async def _run(self, rid: str, cases: list[dict], conditions: list[str], repeats: int, cap: int, dataset: dict) -> None:
        self.store.update_run(rid, status="running")
        calls_made, done = 0, 0
        cancel = self._cancel[rid]
        calib_ids = [c["id"] for c in dataset["cases"] if c["split"] == "calib"]
        warm_evidence = self.store.calibration_evidence(self.router.provider.name, calib_ids) if "adaptive_warm" in conditions else None
        final_status, error = "completed", None
        try:
            for rep in range(repeats):
                for case in cases:
                    for cond in conditions:
                        if cancel.is_set():
                            final_status = "cancelled"
                            raise _Stop
                        if calls_made + (1 if cond.startswith("fixed:") else len(self.settings.tiers)) > cap:
                            final_status, error = "budget_stopped", f"call cap {cap} reached"
                            raise _Stop
                        spec = self._spec(case, cond, rid, rep, warm_evidence)
                        outcome = await self.router.run(spec)
                        calls_made += outcome.totals["calls"]
                        done += 1
                        self.store.update_run(rid, calls_made=calls_made, progress_done=done)
                        if outcome.status == "budget_blocked":
                            final_status, error = "budget_stopped", "daily budget reached"
                            raise _Stop
        except _Stop:
            pass
        except Exception as exc:  # pragma: no cover - surfaced in UI
            log.exception("benchmark failed")
            final_status, error = "failed", f"{type(exc).__name__}: {exc}"

        summary = self.summarize(rid)
        self.store.update_run(rid, status=final_status, error=error, finished_at=time.time(), summary_json=summary)
        self._export(rid)

    def _spec(self, case: dict, cond: str, rid: str, rep: int, warm_evidence: dict | None) -> WorkloadSpec:
        base = dict(task=case["task"], category=case["category"], output_format=case.get("output_format", "text"),
                    checks=case["checks"], source="benchmark", run_id=rid, condition=cond, case_id=case["id"], repeat=rep)
        if cond.startswith("fixed:"):
            return WorkloadSpec(**base, forced_tier=cond.split(":", 1)[1], allow_escalation=False, evidence_override={})
        if cond == "adaptive_warm":
            return WorkloadSpec(**base, quality_threshold=0.8, allow_escalation=True, evidence_override=warm_evidence or {})
        return WorkloadSpec(**base, quality_threshold=0.8, allow_escalation=True, evidence_override={})

    def summarize(self, rid: str) -> dict:
        run = self.store.get_run(rid)
        rows = self.store.workloads_for_run(rid)
        by_cond: dict[str, list[dict]] = {}
        for r in rows:
            by_cond.setdefault(r["condition"], []).append(r)
        baseline = f"fixed:{self.settings.baseline_tier}"
        summary = {
            "provider": run["provider"] if run else None,
            "sample_data": (run or {}).get("provider") != "nebius",
            "baseline": baseline,
            "conditions": {c: condition_summary(rs) for c, rs in by_cond.items()},
            "by_category": {c: by_category(rs) for c, rs in by_cond.items()},
            "comparisons": {},
        }
        if baseline in by_cond:
            for c, rs in by_cond.items():
                if c != baseline:
                    summary["comparisons"][c] = compare(rs, by_cond[baseline])
        return summary

    def _export(self, rid: str) -> None:
        try:
            out_dir = results_dir()
            out_dir.mkdir(parents=True, exist_ok=True)
            run = self.store.get_run(rid)
            rows = self.store.workloads_for_run(rid)
            payload = {"run": run, "workloads": rows}
            (out_dir / f"run-{rid}-{run['provider']}.json").write_text(json.dumps(payload, indent=2, default=str))
        except Exception:  # pragma: no cover
            log.exception("could not export benchmark results")
