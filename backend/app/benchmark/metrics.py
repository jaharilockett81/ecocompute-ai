"""Benchmark metrics computed only from stored workload records."""
from __future__ import annotations

import math
import random
import statistics
from collections import Counter, defaultdict


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def condition_summary(rows: list[dict]) -> dict:
    n = len(rows)
    completed = [r for r in rows if r["status"] in ("passed", "failed")]
    passed = sum(1 for r in rows if r["status"] == "passed")
    lat = [r["latency_ms"] for r in completed if r.get("latency_ms")]
    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    cost_complete = len(costs) == n
    total_cost = sum(costs) if costs else None
    tok_in = sum(r.get("prompt_tokens") or 0 for r in rows)
    tok_out = sum(r.get("completion_tokens") or 0 for r in rows)
    return {
        "n": n,
        "passed": passed,
        "errors": sum(1 for r in rows if r["status"] in ("error", "budget_blocked")),
        "success_rate": round(passed / n, 4) if n else None,
        "success_ci95": wilson(passed, n),
        "latency_ms_mean": round(statistics.fmean(lat), 1) if lat else None,
        "latency_ms_median": round(statistics.median(lat), 1) if lat else None,
        "latency_ms_p95": round(percentile(lat, 0.95), 1) if len(lat) >= 20 else None,
        "prompt_tokens": tok_in,
        "completion_tokens": tok_out,
        "reasoning_tokens": sum(r.get("reasoning_tokens") or 0 for r in rows),
        "tokens_per_task": round((tok_in + tok_out) / n, 1) if n else None,
        "usage_complete": all(r.get("usage_complete") for r in rows),
        "total_cost_usd": round(total_cost, 6) if total_cost is not None else None,
        "cost_complete": cost_complete,
        "overhead_cost_usd": round(sum(r.get("overhead_cost_usd") or 0 for r in rows), 6),
        "cost_per_success_usd": round(total_cost / passed, 6) if total_cost is not None and passed else None,
        "cost_per_task_usd": round(total_cost / n, 8) if total_cost is not None and n else None,
        "quality_failures": [{"case_id": r["case_id"], "repeat": r.get("repeat", 0), "category": r.get("category"),
                              "status": r["status"], "final_tier": r.get("final_tier"), "eval_method": r.get("eval_method")}
                             for r in rows if r["status"] != "passed"],
        "calls": sum(r.get("calls") or 0 for r in rows),
        "calls_per_task": round(sum(r.get("calls") or 0 for r in rows) / n, 3) if n else None,
        "escalation_rate": round(sum(1 for r in rows if (r.get("escalations") or 0) > 0) / n, 4) if n else None,
        "final_tier_distribution": dict(Counter(r.get("final_tier") or "none" for r in rows)),
        "initial_tier_distribution": dict(Counter(r.get("initial_tier") or "none" for r in rows)),
    }


def by_category(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r.get("category") or "unknown"].append(r)
    return {
        cat: {
            "n": len(g),
            "success_rate": round(sum(1 for r in g if r["status"] == "passed") / len(g), 4),
            "total_cost_usd": round(sum(r.get("cost_usd") or 0 for r in g), 6),
            "tokens": sum((r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) for r in g),
            "latency_ms_mean": round(statistics.fmean([r["latency_ms"] for r in g if r.get("latency_ms")] or [0]), 1),
            "final_tiers": dict(Counter(r.get("final_tier") or "none" for r in g)),
        }
        for cat, g in sorted(groups.items())
    }


def _rel(new: float | None, base: float | None) -> float | None:
    if new is None or base in (None, 0):
        return None
    return round((new - base) / base, 4)


def paired_bootstrap(pairs: list[tuple[float, float]], stat: str, iters: int = 2000, seed: int = 7) -> tuple[float, float] | None:
    """95% CI for a paired statistic over resampled task pairs (new, base).
    stat='diff_mean' -> mean(new - base); stat='ratio_sum' -> sum(new)/sum(base) - 1."""
    if len(pairs) < 5:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(iters):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        if stat == "diff_mean":
            vals.append(sum(a - b for a, b in sample) / len(sample))
        else:
            sb = sum(b for _, b in sample)
            if sb == 0:
                continue
            vals.append(sum(a for a, _ in sample) / sb - 1)
    if not vals:
        return None
    vals.sort()
    return (round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4))


def compare(rows_new: list[dict], rows_base: list[dict]) -> dict:
    s_new, s_base = condition_summary(rows_new), condition_summary(rows_base)
    base_by_key = {(r["case_id"], r.get("repeat", 0)): r for r in rows_base}
    pairs = [(r, base_by_key[(r["case_id"], r.get("repeat", 0))]) for r in rows_new if (r["case_id"], r.get("repeat", 0)) in base_by_key]
    succ_pairs = [(float(a["status"] == "passed"), float(b["status"] == "passed")) for a, b in pairs]
    cost_pairs = [(a["cost_usd"], b["cost_usd"]) for a, b in pairs if a.get("cost_usd") is not None and b.get("cost_usd") is not None]
    tok_pairs = [((a.get("prompt_tokens") or 0) + (a.get("completion_tokens") or 0), (b.get("prompt_tokens") or 0) + (b.get("completion_tokens") or 0)) for a, b in pairs]
    lat_pairs = [(a["latency_ms"], b["latency_ms"]) for a, b in pairs if a.get("latency_ms") and b.get("latency_ms")]
    outcome = Counter()
    gains, losses = [], []
    for a, b in pairs:
        pa, pb = a["status"] == "passed", b["status"] == "passed"
        outcome["both_pass" if pa and pb else "both_fail" if not pa and not pb else "only_new_pass" if pa else "only_baseline_pass"] += 1
        if pa and not pb:
            gains.append(a["case_id"])
        if pb and not pa:
            losses.append(a["case_id"])
    return {
        "paired_tasks": len(pairs),
        "paired_outcomes": {"both_pass": outcome["both_pass"], "both_fail": outcome["both_fail"],
                            "only_new_pass": outcome["only_new_pass"], "only_baseline_pass": outcome["only_baseline_pass"],
                            "gains": sorted(gains), "losses": sorted(losses)},
        "success_rate_diff": round((s_new["success_rate"] or 0) - (s_base["success_rate"] or 0), 4) if s_new["n"] and s_base["n"] else None,
        "success_rate_diff_ci95": paired_bootstrap(succ_pairs, "diff_mean"),
        "cost_rel_change": _rel(s_new["total_cost_usd"], s_base["total_cost_usd"]),
        "cost_rel_change_ci95": paired_bootstrap(cost_pairs, "ratio_sum"),
        "cost_per_success_rel_change": _rel(s_new["cost_per_success_usd"], s_base["cost_per_success_usd"]),
        "tokens_rel_change": _rel(sum(a for a, _ in tok_pairs), sum(b for _, b in tok_pairs)),
        "tokens_rel_change_ci95": paired_bootstrap(tok_pairs, "ratio_sum"),
        "latency_mean_rel_change": _rel(s_new["latency_ms_mean"], s_base["latency_ms_mean"]),
        "latency_rel_change_ci95": paired_bootstrap(lat_pairs, "ratio_sum"),
    }
