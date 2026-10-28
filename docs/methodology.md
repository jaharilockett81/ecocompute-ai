# EcoCompute AI: Methodology

This document explains how EcoCompute decides which model to call, how it judges quality, how the benchmark is run, and what the environmental numbers do and do not mean. The same content is served in the app's Methodology page, with the impact parameters read live from the backend.

## 1. Routing policy

Code: `backend/app/router/policy.py`.

For each tier *i* (small → medium → large) the router holds:

- `p_i`: the probability that the tier's output passes the quality gate for this task category, and
- `c_i`: its expected cost per call (expected prompt + completion tokens × configured price; a relative proxy when no price is configured).

Starting at tier *s* and escalating on failure:

```
E[cost | s] = Σ_{k=s..K} c_k · Π_{j=s..k-1} (1 − p_j)
P[pass | s] = 1 − Π_{k=s..K} (1 − p_k)
```

The router picks the start tier with the lowest expected cost that:

1. meets the caller's quality target on `P[pass | s]`,
2. has its own first-attempt pass probability ≥ `min_start_pass` (default 0.5), since a cheap call that usually fails still wastes compute and roughly doubles latency, and
3. fits the per-workload budget and any latency limit.

If no start tier qualifies, it starts at the tier with the highest success probability.

### Pass probabilities

`p_i` is the mean of a Beta posterior:

```
a = k · prior + passes
b = k · (1 − prior) + (n − passes)
p = a / (a + b)            with k = 4 (PRIOR_STRENGTH)
```

The prior is a documented heuristic table per (category, tier), lowered for complex tasks (`COMPLEXITY_PENALTY`). It is an assumption to bootstrap routing, not a trained model, and it fades as evidence accumulates. Once a (category, tier) has three or more graded attempts, expected token counts switch from priors to observed averages.

Reasoning models emit hidden reasoning tokens, so the prior multiplies expected completion tokens by a per-tier verbosity factor. Reasoning tokens are recorded separately and counted in cost, since they are billed as completion tokens.

### Workload analysis

Code: `backend/app/router/analyzer.py`. Keyword and structure rules assign a category (unless the caller sets one), a complexity score in [0, 1], and an expected output length. Every rule that fires is recorded in `signals` and shown in the trace.

## 2. Quality gate

Code: `backend/app/evaluation/`.

| Validator | Checks |
| --- | --- |
| `json_schema` | Output parses as JSON and validates against a JSON Schema |
| `json_fields` | Values at dotted paths equal expected values (numeric tolerance where relevant) |
| `exact`, `label`, `numeric`, `regex` | Final answer matches exactly, as a label, within numeric tolerance, or by pattern |
| `contains_all` | Required terms appear |
| `word_limit`, `bullet_count` | Length and format constraints |
| `python_tests` | Model-written Python passes fixed unit tests in a sandbox |

The Python sandbox screens the AST for OS, network and filesystem access, runs a separate interpreter in isolated mode with an empty environment in a temporary directory, applies CPU, memory, file-size and process limits, and enforces a wall-clock timeout. Only benchmark-defined tests are ever run; the Playground cannot submit tests. It can be disabled with `ECOCOMPUTE_ENABLE_CODE_EXECUTION=false`.

Tasks with no deterministic check are marked **unverified**. An optional model judge can score them; its verdict is labelled an estimate and its cost is counted as overhead. Benchmark cases all have deterministic checks, so the judge never affects benchmark results.

On failure the engine may make one bounded repair on the same tier (structural failures only, with the validator's message as feedback), then escalates to the next tier with a fresh prompt.

## 3. Benchmark

Code: `backend/app/benchmark/`. Dataset: `benchmarks/datasets/ecobench-v1.json`.

- **EcoBench v1:** 49 original, synthetic tasks written for this project: 7 categories (extraction, summarization, classification, structured JSON, reasoning, coding, data interpretation) × 7 cases. 14 calibration cases and 35 held-out test cases (2 and 5 per category).
- **Conditions:**
  - `fixed:<tier>`: always the same model, no escalation.
  - `adaptive`: EcoCompute routing from the prior only (cold start).
  - `adaptive_warm`: routing with evidence from the calibration split only. No test case ever informs its own routing.
- **Pairing:** every condition runs the same cases at temperature 0, so comparisons are paired per task.
- **Statistics:** pass rates with Wilson 95% intervals; differences versus the baseline (`fixed:large`) with paired bootstrap 95% intervals over tasks for pass rate, cost, tokens and latency.
- **Cost:** provider-reported tokens × configured price per million tokens. A condition's cost is marked incomplete if any call lacked usage or price.
- **Guardrails:** a call cap per run, the daily budget and the per-workload budget all stop spending before a paid call.
- **Mock runs:** runs on the offline mock provider are tagged `provider: mock` and `sample_data: true` everywhere, and are never reported as results.

## 4. Environmental impact

Code: `backend/app/sustainability/estimator.py`. Three categories are kept separate.

**A. Directly measured.** Calls, provider-reported tokens (including reasoning tokens), API latency, and cost.

**B. Model-derived estimate.** Per call:

```
FLOPs              ≈ 2 × N_active × tokens         (prefill and decode separately)
E_accel [J]        = FLOPs_prefill / (η_peak × MFU_prefill) + FLOPs_decode / (η_peak × MFU_decode)
E_system           = E_accel × system_overhead
CO2e [g]           = E_system [kWh] × grid_intensity [g/kWh]
Water [mL]         = E_system [kWh] × WUE [L/kWh] × 1000
```

`η_peak` ≈ 989 TFLOPS dense BF16 / 700 W (H100 SXM). `N_active` is read from the model ID (e.g. `A3B` = 3B active parameters) and must be confirmed on the model card.

| Scenario | MFU prefill | MFU decode | System overhead | Grid gCO₂e/kWh | WUE L/kWh |
| --- | --- | --- | --- | --- | --- |
| low | 0.50 | 0.30 | 1.5× | 50 | 0.2 |
| central | 0.35 | 0.12 | 2.4× | 400 | 1.1 |
| high | 0.20 | 0.04 | 3.0× | 800 | 1.8 |

Calls without usage or with unknown active parameters are counted as "not estimable", never guessed.

**C. Not observable through the API.** Actual accelerator power, batch size and co-tenancy, the serving site's PUE and cooling water, and the real-time grid mix.

**Why not latency × GPU power?** API latency includes queueing, network and batching with other tenants; multiplying it by GPU power would attribute a whole accelerator to one request.

### Sources

- Google Cloud, *Measuring the environmental impact of AI inference* (Aug 2025): system-overhead factor (~2.4×), sanity anchor, implied water intensity. https://cloud.google.com/blog/products/infrastructure/measuring-the-environmental-impact-of-ai-inference
- NVIDIA H100 Tensor Core GPU datasheet: peak efficiency anchor. https://www.nvidia.com/en-us/data-center/h100/
- Our World in Data / Ember, carbon intensity of electricity: where to look up a regional grid intensity. https://ourworldindata.org/grapher/carbon-intensity-electricity

## 5. Limitations

- 35 held-out tasks give wide intervals. Differences whose CI crosses zero are not claimed.
- The analyzer is keyword-based and can misclassify; callers can set the category.
- Priors are hand-set; they matter most for the cold `adaptive` condition.
- Model IDs and prices are configuration, verified against the authenticated Nebius catalog by `scripts/verify_nebius.py` and the Settings page.
- Environmental figures are scenario estimates, shown with their bounds.
