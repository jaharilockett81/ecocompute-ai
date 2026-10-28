"""EnvironmentalImpactEstimator — separates what is measured from what is estimated.

Category A (measured): tokens, calls, latency, failures, cost computed from
  provider-reported tokens × configured price.
Category B (model-derived estimate): energy, carbon and water from an explicit,
  editable compute model. Always reported as low / central / high scenarios.
Category C (not observable through an API): actual GPU power draw, actual
  cooling water, actual emissions attributable to a specific request.

Energy model (per call):
    FLOPs ≈ 2 × N_active × tokens                      (standard transformer forward-pass estimate)
    E_accel [J] = FLOPs_prefill / (η_peak × MFU_prefill) + FLOPs_decode / (η_peak × MFU_decode)
    E_system   = E_accel × system_overhead            (host CPU/RAM, idle capacity, PUE)
    CO2e [g]   = E_system [kWh] × grid_intensity [g/kWh]
    Water [mL] = E_system [kWh] × WUE [L/kWh] × 1000

Why not latency × GPU power? Hosted inference batches many requests on the
same accelerators, and API latency includes queueing and network time. Wall-clock
latency × device power would attribute an entire GPU to one request and badly
overestimate. A FLOPs-based model scales with work actually requested.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# Peak efficiency anchor: NVIDIA H100 SXM spec sheet — ~989 TFLOPS dense BF16 at 700 W TDP.
H100_BF16_FLOP_PER_J = 989e12 / 700.0

SOURCES = [
    {
        "id": "google-2025",
        "title": "Google Cloud — Measuring the environmental impact of AI inference (Aug 2025)",
        "url": "https://cloud.google.com/blog/products/infrastructure/measuring-the-environmental-impact-of-ai-inference",
        "used_for": "System-overhead factor: full-system 0.24 Wh vs accelerator-only 0.10 Wh per median Gemini text prompt (≈2.4×); order-of-magnitude sanity anchor; implied water intensity ≈1.1 L/kWh.",
    },
    {
        "id": "nvidia-h100",
        "title": "NVIDIA H100 Tensor Core GPU datasheet",
        "url": "https://www.nvidia.com/en-us/data-center/h100/",
        "used_for": "Peak efficiency anchor η_peak ≈ 989 TFLOPS dense BF16 / 700 W.",
    },
    {
        "id": "owid-ember",
        "title": "Our World in Data / Ember — Carbon intensity of electricity generation",
        "url": "https://ourworldindata.org/grapher/carbon-intensity-electricity",
        "used_for": "Where to look up a region-specific grid intensity to replace the scenario bounds.",
    },
]


@dataclass(frozen=True)
class Scenario:
    name: str
    mfu_prefill: float
    mfu_decode: float
    system_overhead: float
    grid_g_per_kwh: float
    wue_l_per_kwh: float


DEFAULT_SCENARIOS = (
    Scenario("low", mfu_prefill=0.50, mfu_decode=0.30, system_overhead=1.5, grid_g_per_kwh=50, wue_l_per_kwh=0.2),
    Scenario("central", mfu_prefill=0.35, mfu_decode=0.12, system_overhead=2.4, grid_g_per_kwh=400, wue_l_per_kwh=1.1),
    Scenario("high", mfu_prefill=0.20, mfu_decode=0.04, system_overhead=3.0, grid_g_per_kwh=800, wue_l_per_kwh=1.8),
)

ASSUMPTIONS = [
    "Active parameters per tier are read from the model ID naming (e.g. 'A3B' = 3B active) and must be verified on the model card.",
    "Hardware efficiency is anchored to H100 BF16 peak; Nebius may serve on other accelerators or precisions (FP8, H200, B200), which would lower energy per FLOP.",
    "MFU (model FLOPs utilization) ranges are scenario assumptions: prefill is compute-bound and more efficient; decode is memory-bandwidth-bound and less efficient.",
    "System overhead central value 2.4× is the ratio Google reported between full-system and accelerator-only energy for Gemini; Nebius's ratio is unknown.",
    "Grid intensity bounds (50/400/800 gCO2e/kWh) are illustrative of low-carbon, mid, and coal-heavy grids — not Nebius's actual supply mix.",
    "Water use efficiency bounds (0.2/1.1/1.8 L/kWh, on-site) are scenario values; central is implied by Google's published per-prompt figures.",
    "Hidden reasoning tokens are included because they are generated (and billed) as completion tokens.",
]

NOT_OBSERVABLE = [
    "Actual accelerator power draw for any request (no infrastructure telemetry through the API).",
    "Batch size and co-tenancy on the serving GPUs.",
    "Actual data-center cooling water and PUE for the serving region.",
    "Real-time grid mix and any renewable energy contracts at the serving site.",
]


@dataclass
class ScenarioResult:
    scenario: str
    energy_wh: float
    co2e_g: float
    water_ml: float


class EnvironmentalImpactEstimator:
    def __init__(self, active_params_b: dict[str, float | None], scenarios: tuple[Scenario, ...] = DEFAULT_SCENARIOS):
        self.active_params_b = active_params_b  # tier key -> billions of active params
        self.scenarios = scenarios

    def can_estimate(self, tier: str | None) -> bool:
        return bool(tier) and bool(self.active_params_b.get(tier))

    def estimate_call(self, tier: str, prompt_tokens: int, completion_tokens: int) -> list[ScenarioResult] | None:
        n = self.active_params_b.get(tier)
        if not n:
            return None
        n_active = n * 1e9
        out = []
        for sc in self.scenarios:
            e_acc = (2 * n_active * prompt_tokens) / (H100_BF16_FLOP_PER_J * sc.mfu_prefill) + (
                2 * n_active * completion_tokens
            ) / (H100_BF16_FLOP_PER_J * sc.mfu_decode)
            wh = e_acc * sc.system_overhead / 3600.0
            out.append(ScenarioResult(sc.name, wh, wh / 1000 * sc.grid_g_per_kwh, wh / 1000 * sc.wue_l_per_kwh * 1000))
        return out

    def estimate_attempts(self, attempts: list[dict]) -> dict:
        """Aggregate over attempt rows. Calls lacking usage or tier params are counted, not guessed."""
        totals = {sc.name: {"energy_wh": 0.0, "co2e_g": 0.0, "water_ml": 0.0} for sc in self.scenarios}
        covered, skipped = 0, 0
        for a in attempts:
            if not a.get("ok") or a.get("prompt_tokens") is None or a.get("completion_tokens") is None or not self.can_estimate(a.get("tier")):
                skipped += 1
                continue
            res = self.estimate_call(a["tier"], a["prompt_tokens"], a["completion_tokens"])
            covered += 1
            for r in res or []:
                t = totals[r.scenario]
                t["energy_wh"] += r.energy_wh
                t["co2e_g"] += r.co2e_g
                t["water_ml"] += r.water_ml
        return {
            "category": "B — model-derived estimate",
            "calls_estimated": covered,
            "calls_not_estimable": skipped,
            "scenarios": {k: {m: round(v, 6) for m, v in vals.items()} for k, vals in totals.items()},
        }

    def methodology(self) -> dict:
        return {
            "equations": {
                "flops": "FLOPs ≈ 2 × N_active × tokens",
                "accelerator_energy_J": "FLOPs_prefill/(η·MFU_prefill) + FLOPs_decode/(η·MFU_decode)",
                "system_energy": "E_accel × system_overhead",
                "co2e_g": "kWh × grid_intensity",
                "water_ml": "kWh × WUE × 1000",
            },
            "eta_peak_flop_per_joule": H100_BF16_FLOP_PER_J,
            "active_params_b": self.active_params_b,
            "scenarios": [asdict(s) for s in self.scenarios],
            "assumptions": ASSUMPTIONS,
            "not_observable": NOT_OBSERVABLE,
            "sources": SOURCES,
            "why_not_latency": "API latency includes queueing, network and batching with other tenants; latency × GPU power would attribute a whole accelerator to one request.",
        }
