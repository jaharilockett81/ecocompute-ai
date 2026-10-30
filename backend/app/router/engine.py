"""EcoComputeRouter — the closed-loop agent.

Analyze → Select → Execute → Evaluate → (Repair | Escalate) → Record → Update policy

Every step emits a structured event. The full event list is persisted as the
workload's machine-readable decision trace and streamed to the UI.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.core.config import ModelTier, Settings
from app.core.logging import get_logger
from app.evaluation.faults import corrupt_candidate
from app.evaluation.judge import judge_output
from app.evaluation.validators import EvalResult, evaluate
from app.persistence.store import Store
from app.providers.base import ChatResult
from app.router.analyzer import analyze
from app.router.policy import RoutingDecision, plan, prior_pass, PRIOR_STRENGTH

log = get_logger("ecocompute.router")

Emit = Callable[[dict], Awaitable[None]]

SYSTEM_PROMPT = "You are a precise assistant. Follow the requested output format exactly. Be concise."
JSON_INSTRUCTION = "Respond with ONLY a single valid JSON value. No prose, no markdown code fences."


@dataclass
class WorkloadSpec:
    task: str
    category: str | None = None
    output_format: str = "text"  # text | json | code
    checks: list[dict] = field(default_factory=list)
    system: str | None = None
    quality_threshold: float = 0.8
    allow_escalation: bool = True
    max_escalations: int = 2
    repair_attempts: int = 0
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    use_judge: bool = False
    forced_tier: str | None = None
    max_output_tokens: int | None = None
    # Safety drill: corrupt the FIRST real candidate before the gate (labelled, excluded from evidence).
    fault_injection: str | None = None
    # bookkeeping
    source: str = "playground"
    run_id: str | None = None
    condition: str | None = None
    case_id: str | None = None
    repeat: int = 0
    evidence_override: dict | None = None  # benchmark: frozen evidence snapshot (avoids test-set leakage)


@dataclass
class WorkloadOutcome:
    workload_id: str
    status: str
    final_output: str
    final_tier: str | None
    final_model: str | None
    eval: dict | None
    trace: list[dict]
    decision: dict
    totals: dict


class BudgetExceeded(Exception):
    pass


class EcoComputeRouter:
    def __init__(self, settings: Settings, provider, store: Store):
        self.settings = settings
        self.provider = provider
        self.store = store
        self._sem = asyncio.Semaphore(max(1, settings.max_concurrency))

    # ------------------------------------------------------------ evidence
    def evidence(self) -> dict[tuple[str, str], dict]:
        rows = self.store.tier_outcomes(self.provider.name)
        return {(r["category"], r["tier"]): r for r in rows}

    def evidence_summary(self) -> list[dict]:
        """Prior vs posterior pass-rate per (category, tier) for the Model Router page."""
        from app.router.analyzer import CATEGORIES

        ev = self.evidence()
        out = []
        for cat in CATEGORIES:
            for t in self.settings.tiers:
                p0 = prior_pass(cat, t.rank, 0.3)
                e = ev.get((cat, t.key), {})
                n, passes = int(e.get("n") or 0), int(e.get("passes") or 0)
                post = (PRIOR_STRENGTH * p0 + passes) / (PRIOR_STRENGTH + n)
                out.append({
                    "category": cat, "tier": t.key, "label": t.label, "prior_pass": round(p0, 3),
                    "observed_n": n, "observed_passes": passes,
                    "observed_rate": round(passes / n, 3) if n else None, "posterior_pass": round(post, 3),
                    "avg_completion_tokens": e.get("avg_completion"), "avg_latency_ms": e.get("avg_latency"),
                    "avg_cost_usd": e.get("avg_cost"),
                })
        return out

    # --------------------------------------------------------------- run
    async def run(self, spec: WorkloadSpec, emit: Emit | None = None) -> WorkloadOutcome:
        trace: list[dict] = []
        seq = 0

        async def ev(step: str, status: str, title: str, detail: str = "", data: dict | None = None) -> None:
            nonlocal seq
            seq += 1
            event = {"seq": seq, "ts": time.time(), "step": step, "status": status, "title": title, "detail": detail, "data": data or {}}
            trace.append(event)
            if emit:
                await emit(event)

        s = self.settings
        tiers = s.tier_map
        wid = self.store.create_workload(
            source=spec.source, run_id=spec.run_id, condition=spec.condition, case_id=spec.case_id, repeat=spec.repeat,
            task_text=spec.task[:20000], output_format=spec.output_format, provider=self.provider.name,
        )
        await ev("start", "info", "Workload received", f"id {wid}", {"workload_id": wid, "provider": self.provider.name})

        # 1. Analyze
        analysis = analyze(spec.task, spec.category, spec.output_format)
        await ev("analyze", "done", "Workload analysis",
                 f"{analysis.category} · complexity {analysis.complexity:.2f}", analysis.as_dict())

        # 2. Select
        evidence = spec.evidence_override if spec.evidence_override is not None else self.evidence()
        decision: RoutingDecision = plan(
            s.tiers, analysis, evidence,
            quality_threshold=spec.quality_threshold, allow_escalation=spec.allow_escalation,
            max_escalations=spec.max_escalations, max_cost_usd=spec.max_cost_usd or s.max_workload_cost_usd,
            max_latency_ms=spec.max_latency_ms, forced_tier=spec.forced_tier,
            exploration_rate=s.exploration_rate if spec.source == "playground" else 0.0, seed=wid,
            min_start_pass=s.min_start_pass,
        )
        await ev("select", "done", f"Selected {tiers[decision.start_tier].label}", decision.rationale, decision.as_dict())
        self.store.update_workload(wid, category=analysis.category, initial_tier=decision.start_tier,
                                   analysis_json=analysis.as_dict(), decision_json=decision.as_dict())

        messages = self._build_messages(spec)
        max_tokens = min(spec.max_output_tokens or s.max_output_tokens, s.max_output_tokens)
        workload_budget = spec.max_cost_usd or s.max_workload_cost_usd

        totals = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0,
                  "overhead_cost_usd": 0.0, "latency_ms": 0.0, "calls": 0, "escalations": 0, "repairs": 0,
                  "usage_complete": True, "cost_complete": True}
        status, final_output, final_tier, final_model = "failed", "", None, None
        last_eval: EvalResult | None = None
        attempt_idx = 0
        chain = list(decision.chain)
        tier_pos = 0
        repairs_left = spec.repair_attempts

        while tier_pos < len(chain):
            tier = tiers[chain[tier_pos]]
            is_repair = last_eval is not None and final_tier == tier.key
            # Budget guardrails before every paid call.
            try:
                self._check_budget(totals, workload_budget)
            except BudgetExceeded as exc:
                await ev("guardrail", "failed", "Budget guardrail stopped execution", str(exc))
                status = "budget_blocked" if attempt_idx == 0 else status
                break

            await ev("infer", "running", f"{'Repair on' if is_repair else 'Calling'} {tier.label} via Nebius Token Factory",
                     tier.model_id, {"tier": tier.key, "model": tier.model_id, "attempt": attempt_idx + 1})
            async with self._sem:
                result: ChatResult = await self.provider.chat(
                    tier.model_id, messages, max_tokens=max_tokens, temperature=s.temperature,
                )
            attempt_idx += 1
            cost = tier.cost(result.prompt_tokens, result.completion_tokens)
            self._accumulate(totals, result, cost)
            final_tier, final_model = tier.key, result.model or tier.model_id

            call_data = {
                "tier": tier.key, "model": result.model, "provider": result.provider, "ok": result.ok,
                "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
                "reasoning_tokens": result.reasoning_tokens, "latency_ms": round(result.latency_ms, 1),
                "cost_usd": cost, "finish_reason": result.finish_reason, "retries": result.attempts - 1,
                "request_id": result.request_id, "error": result.error,
            }
            if not result.ok:
                await ev("infer", "failed", f"{tier.label} call failed", result.error or "unknown error", call_data)
                self.store.add_attempt(workload_id=wid, idx=attempt_idx, role="primary", tier=tier.key, model=tier.model_id,
                                       provider=result.provider, ok=False, passed=None, latency_ms=result.latency_ms,
                                       error=result.error, category=analysis.category, source=spec.source, case_id=spec.case_id)
                if result.error_type in ("auth", "configuration"):
                    status = "error"
                    break
                tier_pos += 1  # provider-side failure: try the next tier if allowed
                if tier_pos < len(chain):
                    totals["escalations"] += 1
                    await ev("escalate", "info", f"Escalating to {tiers[chain[tier_pos]].label}", "previous call failed at the provider")
                else:
                    status = "error"
                continue

            await ev("infer", "done", f"{tier.label} responded",
                     f"{result.completion_tokens or '?'} output tokens in {result.latency_ms/1000:.2f}s", call_data)
            candidate = result.content
            injected = bool(spec.fault_injection) and attempt_idx == 1
            if injected:
                candidate, fault = corrupt_candidate(result.content, spec.checks)
                await ev("inject", "info", "Injected fault (deliberate safety drill)",
                         "The real answer above was corrupted on purpose before the quality gate. "
                         "This is a test of the gate, not a model failure.", {**fault, "injected": True})
            final_output = candidate

            # 4. Evaluate — model output is untrusted until a deterministic check approves it.
            eval_res = evaluate(candidate, spec.checks, code_execution=s.enable_code_execution)
            if result.finish_reason == "length" and not result.content.strip():
                eval_res = EvalResult(False, eval_res.method, "output truncated at max_tokens before an answer was produced",
                                      0.0, ["truncated"], structural_failure=False)
            passed: bool | None = eval_res.passed if spec.checks else None
            eval_method = eval_res.method

            if not spec.checks and spec.use_judge:
                await ev("evaluate", "running", "Model judge scoring (estimate)", s.judge_model)
                verdict = await judge_output(self.provider, s.judge_model, spec.task, result.content)
                judge_tier = s.tier_for_model(s.judge_model)
                jcost = judge_tier.cost(verdict.call.prompt_tokens, verdict.call.completion_tokens) if judge_tier else None
                self._accumulate(totals, verdict.call, jcost, overhead=True)
                self.store.add_attempt(workload_id=wid, idx=attempt_idx * 100 + 1, role="judge", tier=judge_tier.key if judge_tier else None,
                                       model=s.judge_model, provider=verdict.call.provider, ok=verdict.call.ok, passed=None,
                                       prompt_tokens=verdict.call.prompt_tokens, completion_tokens=verdict.call.completion_tokens,
                                       latency_ms=verdict.call.latency_ms, cost_usd=jcost, eval_detail=verdict.rationale,
                                       error=verdict.call.error, category=analysis.category, source=spec.source, case_id=spec.case_id)
                passed, eval_method = verdict.passed, "model_judge_estimate"
                eval_res = EvalResult(bool(verdict.passed), eval_method,
                                      f"judge score {verdict.score}/5 (estimate): {verdict.rationale}",
                                      (verdict.score or 0) / 5 if verdict.score else None)

            last_eval = eval_res
            self.store.add_attempt(
                workload_id=wid, idx=attempt_idx, role="injected" if injected else "primary", tier=tier.key, model=result.model or tier.model_id,
                provider=result.provider, ok=True, passed=passed, prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens, reasoning_tokens=result.reasoning_tokens,
                latency_ms=result.latency_ms, cost_usd=cost, finish_reason=result.finish_reason,
                eval_method=eval_method, eval_detail=(f"[INJECTED FAULT] " if injected else "") + eval_res.detail[:1000], category=analysis.category, source=spec.source, case_id=spec.case_id,
            )

            if passed is None:
                await ev("evaluate", "info", "No objective check — output accepted unverified",
                         "Add JSON schema, required terms or enable the judge to gate quality.", eval_res.as_dict())
                status = "unverified"
                break
            if passed and injected:
                # The gate accepted a known-bad candidate: a validator defect. Never release it.
                await ev("evaluate", "failed", "Gate defect: injected fault was accepted",
                         "The checks did not catch a deliberately corrupted answer; it is withheld.", eval_res.as_dict())
                status = "error"
                break
            if passed:
                await ev("evaluate", "done", "Quality gate passed", eval_res.detail, eval_res.as_dict())
                await ev("approve", "done", "Approved for release",
                         f"Released only after {eval_method} verification passed", {"approved": True, "method": eval_method})
                status = "passed"
                break

            await ev("evaluate", "failed", "Quality gate rejected the injected candidate" if injected else "Quality gate failed",
                     eval_res.detail, {**eval_res.as_dict(), "injected": injected})

            # 5. Repair (same tier, with validator feedback) or escalate
            if eval_res.structural_failure and repairs_left > 0:
                repairs_left -= 1
                totals["repairs"] += 1
                messages = messages + [
                    {"role": "assistant", "content": result.content[:4000]},
                    {"role": "user", "content": f"Your previous answer failed validation: {eval_res.detail[:400]}. "
                                                f"Return a corrected answer only."},
                ]
                await ev("repair", "info", f"Bounded correction on {tier.label}", f"{repairs_left} repair(s) left after this one")
                continue

            if spec.allow_escalation and tier_pos + 1 < len(chain):
                nxt = tiers[chain[tier_pos + 1]]
                totals["escalations"] += 1
                await ev("escalate", "info", f"Escalating {tier.label} → {nxt.label}",
                         f"Validation failed; escalation {totals['escalations']}/{spec.max_escalations}")
                tier_pos += 1
                messages = self._build_messages(spec)  # fresh prompt for the stronger model
                continue

            reason = "escalation disabled" if not spec.allow_escalation else "no stronger tier left in the chain"
            await ev("final", "failed", "Stopping: quality gate not met", reason)
            status = "failed"
            break

        # 6. Record
        self.store.update_workload(
            wid, status=status, final_tier=final_tier, final_model=final_model,
            prompt_tokens=totals["prompt_tokens"], completion_tokens=totals["completion_tokens"],
            reasoning_tokens=totals["reasoning_tokens"], usage_complete=totals["usage_complete"],
            cost_usd=round(totals["cost_usd"], 8) if totals["cost_complete"] else None,
            overhead_cost_usd=round(totals["overhead_cost_usd"], 8), latency_ms=round(totals["latency_ms"], 1),
            escalations=totals["escalations"], calls=totals["calls"],
            eval_method=last_eval.method if last_eval else None, final_output=final_output[:20000],
        )
        await ev("record", "done", "Recorded measurements",
                 f"{totals['calls']} call(s) · {totals['prompt_tokens'] + totals['completion_tokens']} tokens · "
                 f"{totals['latency_ms']/1000:.2f}s" + (f" · ${totals['cost_usd']:.6f}" if totals["cost_complete"] else ""),
                 dict(totals))

        # 7. Policy update (evidence is read from the attempts table on the next decision)
        if spec.evidence_override is None and final_tier and status in ("passed", "failed"):
            post = {(r["category"], r["tier"]): r for r in self.store.tier_outcomes(self.provider.name)}
            upd = []
            for t in s.tiers:
                e = post.get((analysis.category, t.key))
                if e:
                    p0 = prior_pass(analysis.category, t.rank, analysis.complexity)
                    upd.append({"tier": t.key, "n": e["n"], "passes": e["passes"],
                                "posterior": round((PRIOR_STRENGTH * p0 + e["passes"]) / (PRIOR_STRENGTH + e["n"]), 3)})
            await ev("learn", "done", "Routing evidence updated", f"category '{analysis.category}'", {"category": analysis.category, "tiers": upd})

        final_title = {"passed": "Final answer passed validation", "unverified": "Final answer (unverified)",
                       "failed": "Final answer did not pass validation", "error": "Workload ended with a provider error",
                       "budget_blocked": "Blocked by budget guardrail"}[status]
        await ev("final", "done" if status in ("passed", "unverified") else "failed", final_title,
                 f"{tiers[final_tier].label if final_tier else '—'}", {"status": status, "final_tier": final_tier, "final_model": final_model})
        self.store.update_workload(wid, trace_json=trace)

        return WorkloadOutcome(wid, status, final_output, final_tier, final_model,
                               last_eval.as_dict() if last_eval else None, trace, decision.as_dict(), totals)

    # ------------------------------------------------------------ helpers
    def _build_messages(self, spec: WorkloadSpec) -> list[dict]:
        system = spec.system or SYSTEM_PROMPT
        if spec.output_format == "json":
            system += " " + JSON_INSTRUCTION
        elif spec.output_format == "code":
            system += " Return only the code in a single ```python block."
        return [{"role": "system", "content": system}, {"role": "user", "content": spec.task}]

    @staticmethod
    def _accumulate(totals: dict, r: ChatResult, cost: float | None, overhead: bool = False) -> None:
        totals["calls"] += 1
        totals["latency_ms"] += r.latency_ms
        if r.ok:
            if r.usage_reported:
                totals["prompt_tokens"] += r.prompt_tokens or 0
                totals["completion_tokens"] += r.completion_tokens or 0
                totals["reasoning_tokens"] += r.reasoning_tokens or 0
            else:
                totals["usage_complete"] = False
            if cost is None:
                totals["cost_complete"] = False
            else:
                totals["cost_usd"] += cost
                if overhead:
                    totals["overhead_cost_usd"] += cost

    def _check_budget(self, totals: dict, workload_budget: float) -> None:
        if self.provider.name != "nebius":
            return
        spent_today = self.store.spend_today_usd()
        if spent_today >= self.settings.daily_budget_usd:
            raise BudgetExceeded(f"daily budget ${self.settings.daily_budget_usd:.2f} reached (spent ${spent_today:.4f})")
        if totals["cost_usd"] >= workload_budget:
            raise BudgetExceeded(f"workload budget ${workload_budget:.4f} reached (spent ${totals['cost_usd']:.6f})")
