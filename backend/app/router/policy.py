"""Routing policy: expected-cost minimisation over the escalation ladder.

For each model tier i we hold an estimate p_i of the probability that its
output passes the quality gate for this task category, and an estimated cost
c_i per call. Starting at tier s and escalating on failure, the expected
cost and success probability of the chain are

    E[cost | s]  = Σ_{k=s..K} c_k · Π_{j=s..k-1} (1 - p_j)
    P[pass | s]  = 1 - Π_{k=s..K} (1 - p_k)

The policy picks the start tier with the lowest expected cost whose success
probability meets the caller's quality threshold, whose own first-attempt pass
probability is at least `min_start_pass` (default 0.5 — cheap-but-likely-to-fail
first calls waste compute and double latency even when they are cheap) (and whose expected cost and
latency fit their limits). If none qualifies, it starts at the tier with the
highest success probability.

p_i is a Beta posterior mean: a heuristic prior (documented below, NOT a
trained model) with pseudo-count strength PRIOR_STRENGTH, updated with the
observed pass/fail counts for (category, tier). As evidence accumulates the
data dominates the prior.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

from app.core.config import ModelTier
from app.router.analyzer import WorkloadAnalysis

PRIOR_STRENGTH = 4.0

# Heuristic prior pass-rates by category and tier rank (0=small, 1=medium, 2=large).
# These are assumptions to bootstrap routing; they are shown in the UI and
# replaced by measured pass rates as evidence accumulates.
PRIOR_PASS = {
    "extraction":          (0.80, 0.90, 0.93),
    "summarization":       (0.80, 0.88, 0.92),
    "classification":      (0.85, 0.92, 0.94),
    "structured_json":     (0.72, 0.88, 0.92),
    "reasoning":           (0.50, 0.75, 0.88),
    "coding":              (0.55, 0.78, 0.88),
    "data_interpretation": (0.60, 0.80, 0.90),
    "general":             (0.70, 0.85, 0.90),
}
# How strongly task complexity erodes each tier's prior pass rate.
COMPLEXITY_PENALTY = (0.45, 0.25, 0.12)
# Reasoning models emit hidden reasoning tokens; prior multiplier on completion tokens by rank.
VERBOSITY_PRIOR = (2.0, 2.5, 3.0)
# Relative cost proxy when a tier has no configured price (flagged as unpriced in the trace).
UNPRICED_COST_WEIGHT = (1.0, 5.0, 15.0)


@dataclass
class TierEstimate:
    tier: str
    model_id: str
    label: str
    rank: int
    prior_pass: float
    observed_n: int
    observed_passes: int
    pass_prob: float
    est_prompt_tokens: float
    est_completion_tokens: float
    token_source: str  # "prior" | "observed"
    est_cost_usd: float | None
    cost_proxy: float  # the quantity actually minimised (USD if priced, relative units if not)
    est_latency_ms: float | None


@dataclass
class StartOption:
    start_tier: str
    chain: list[str]
    expected_cost: float
    expected_cost_usd: float | None
    success_prob: float
    expected_latency_ms: float | None
    feasible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    start_tier: str
    chain: list[str]
    rationale: str
    estimates: list[TierEstimate]
    options: list[StartOption]
    explored: bool
    forced: bool
    cost_units: str  # "usd" | "relative"

    def as_dict(self) -> dict:
        return {
            "start_tier": self.start_tier,
            "chain": self.chain,
            "rationale": self.rationale,
            "explored": self.explored,
            "forced": self.forced,
            "cost_units": self.cost_units,
            "estimates": [asdict(e) for e in self.estimates],
            "options": [asdict(o) for o in self.options],
        }


def prior_pass(category: str, rank: int, complexity: float) -> float:
    base = PRIOR_PASS.get(category, PRIOR_PASS["general"])
    r = min(rank, len(base) - 1)
    penalty = COMPLEXITY_PENALTY[min(rank, len(COMPLEXITY_PENALTY) - 1)]
    return max(0.05, min(0.98, base[r] - penalty * max(0.0, complexity - 0.2)))


def estimate_tiers(
    tiers: tuple[ModelTier, ...],
    analysis: WorkloadAnalysis,
    evidence: dict[tuple[str, str], dict],
) -> list[TierEstimate]:
    all_priced = all(t.priced for t in tiers)
    out: list[TierEstimate] = []
    for t in sorted(tiers, key=lambda x: x.rank):
        p0 = prior_pass(analysis.category, t.rank, analysis.complexity)
        ev = evidence.get((analysis.category, t.key), {})
        n, passes = int(ev.get("n") or 0), int(ev.get("passes") or 0)
        a = PRIOR_STRENGTH * p0 + passes
        b = PRIOR_STRENGTH * (1 - p0) + (n - passes)
        p = a / (a + b)

        if n >= 3 and ev.get("avg_prompt") and ev.get("avg_completion"):
            est_in, est_out, src = float(ev["avg_prompt"]), float(ev["avg_completion"]), "observed"
            latency = float(ev["avg_latency"]) if ev.get("avg_latency") else None
        else:
            est_in = analysis.input_tokens_est + 60
            est_out = analysis.expected_output_tokens * VERBOSITY_PRIOR[min(t.rank, 2)]
            src, latency = "prior", None

        usd = t.cost(round(est_in), round(est_out)) if all_priced else None
        proxy = usd if usd is not None else (est_in + est_out) * UNPRICED_COST_WEIGHT[min(t.rank, 2)] / 1000
        out.append(TierEstimate(t.key, t.model_id, t.label, t.rank, round(p0, 3), n, passes, round(p, 3),
                                round(est_in, 1), round(est_out, 1), src, usd, proxy, latency))
    return out


def plan(
    tiers: tuple[ModelTier, ...],
    analysis: WorkloadAnalysis,
    evidence: dict[tuple[str, str], dict],
    *,
    quality_threshold: float = 0.8,
    allow_escalation: bool = True,
    max_escalations: int = 2,
    max_cost_usd: float | None = None,
    max_latency_ms: float | None = None,
    forced_tier: str | None = None,
    exploration_rate: float = 0.0,
    seed: str = "",
    min_start_pass: float = 0.5,
) -> RoutingDecision:
    est = estimate_tiers(tiers, analysis, evidence)
    by_key = {e.tier: e for e in est}
    keys = [e.tier for e in est]
    units = "usd" if all(e.est_cost_usd is not None for e in est) else "relative"

    if forced_tier:
        if forced_tier not in by_key:
            raise ValueError(f"unknown tier {forced_tier}")
        chain = [forced_tier] if not allow_escalation else keys[keys.index(forced_tier):][: max_escalations + 1]
        return RoutingDecision(forced_tier, chain, f"Fixed-model condition: always start on {by_key[forced_tier].label}.",
                               est, [], explored=False, forced=True, cost_units=units)

    options: list[StartOption] = []
    for i, k in enumerate(keys):
        chain = keys[i:][: (max_escalations + 1) if allow_escalation else 1]
        exp_cost, exp_usd, exp_lat, survive = 0.0, 0.0, 0.0, 1.0
        usd_known, lat_known = True, True
        for ck in chain:
            e = by_key[ck]
            exp_cost += survive * e.cost_proxy
            if e.est_cost_usd is None:
                usd_known = False
            else:
                exp_usd += survive * e.est_cost_usd
            if e.est_latency_ms is None:
                lat_known = False
            else:
                exp_lat += survive * e.est_latency_ms
            survive *= 1 - e.pass_prob
        success = 1 - survive
        reasons, feasible = [], True
        if allow_escalation and len(chain) > 1 and by_key[k].pass_prob < min_start_pass:
            feasible = False
            reasons.append(f"{by_key[k].label} P(pass) {by_key[k].pass_prob:.2f} < {min_start_pass:.2f} first-attempt floor (a likely-failing first call wastes compute and doubles latency)")
        if success < quality_threshold:
            feasible = False
            reasons.append(f"P(pass) {success:.2f} < threshold {quality_threshold:.2f}")
        if max_cost_usd is not None and usd_known and exp_usd > max_cost_usd:
            feasible = False
            reasons.append(f"expected ${exp_usd:.5f} > budget ${max_cost_usd:.5f}")
        if max_latency_ms is not None and lat_known and exp_lat > max_latency_ms:
            feasible = False
            reasons.append(f"expected {exp_lat:.0f} ms > limit {max_latency_ms:.0f} ms")
        options.append(StartOption(k, chain, round(exp_cost, 8), round(exp_usd, 8) if usd_known else None,
                                   round(success, 4), round(exp_lat, 1) if lat_known else None, feasible, reasons))

    feasible = [o for o in options if o.feasible]
    if feasible:
        best = min(feasible, key=lambda o: (o.expected_cost, -o.success_prob))
        rationale = (
            f"Start on {by_key[best.start_tier].label}: lowest expected cost among plans meeting the "
            f"{quality_threshold:.0%} quality target (P(pass)={best.success_prob:.2f} with "
            f"{'escalation via ' + ' → '.join(by_key[c].label for c in best.chain[1:]) if len(best.chain) > 1 else 'no escalation'})."
        )
    else:
        best = max(options, key=lambda o: (o.success_prob, -o.expected_cost))
        rationale = (f"No plan meets the {quality_threshold:.0%} target within limits; starting on "
                     f"{by_key[best.start_tier].label}, the highest-probability option (P(pass)={best.success_prob:.2f}).")

    explored = False
    if exploration_rate > 0:
        roll = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        cheaper = [o for o in options if by_key[o.start_tier].rank < by_key[best.start_tier].rank
                   and by_key[o.start_tier].observed_n < 5 and allow_escalation
                   and (max_cost_usd is None or o.expected_cost_usd is None or o.expected_cost_usd <= max_cost_usd)]
        if cheaper and roll < exploration_rate:
            pick = max(cheaper, key=lambda o: by_key[o.start_tier].rank)
            explored = True
            rationale = (f"Exploration (rate {exploration_rate:.0%}): trying {by_key[pick.start_tier].label} which has only "
                         f"{by_key[pick.start_tier].observed_n} observations for '{analysis.category}'; escalation protects quality. "
                         f"Greedy choice would have been {by_key[best.start_tier].label}.")
            best = pick

    return RoutingDecision(best.start_tier, best.chain, rationale, est, options, explored, False, units)
