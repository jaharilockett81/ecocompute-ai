# Design decisions

Short records of the choices that shaped EcoCompute AI and what they cost.

## D1. Route on expected cost of the whole escalation chain, not on a single model's cost

A start tier is only cheap if it usually passes; otherwise you pay for it *and* the escalation. The policy minimises `E[cost | start]` over the full chain subject to a quality target, which makes "start small" the answer only when the evidence supports it.
**Trade-off:** needs per-tier pass probabilities, which are uncertain early on (see D2).

## D2. Beta posteriors with a visible heuristic prior

Pass probabilities start from a hand-set prior per (category, tier) with pseudo-count 4 and update with every graded attempt. Priors are shown in the trace and the Router page and labelled as assumptions.
**Alternatives considered:** a trained classifier (no labelled data, opaque) and a router LLM call per request (adds cost and latency to every task).
**Trade-off:** the cold `adaptive` condition depends on hand-set priors; `adaptive_warm` exists to show what calibration evidence adds.

## D3. A first-attempt pass floor (default 50%)

Pure expected-cost minimisation will sometimes start on a model that fails most of the time because it is very cheap. That still burns tokens and roughly doubles latency. The floor rules those plans out.
**Trade-off:** occasionally forgoes a marginally cheaper plan.

## D4. Deterministic quality gates first, model judge only as a labelled estimate

Escalation decisions and benchmark numbers must be reproducible and defensible, so they rest on validators (schema, exact fields, numeric tolerance, unit tests). The judge is opt-in, used only when no check exists, marked as an estimate, and its cost is counted as overhead.
**Trade-off:** open-ended tasks without checks end up "unverified" rather than graded.

## D5. Sandboxed execution for code tasks

Coding cases run model output against fixed unit tests: AST screen, isolated interpreter, empty env, temp dir, resource limits, timeout. Only dataset-defined tests run; the Playground cannot submit tests; the feature can be disabled.
**Trade-off:** a subprocess sandbox is not a VM. For a public deployment it is defence in depth, not a guarantee.

## D6. Original benchmark with a calibration/test split

EcoBench v1 is 49 synthetic tasks written for this project (no licensing issues, no contamination from public sets), each with an objective check. Calibration cases may warm the router; test cases are held out. All conditions run the same cases so comparisons are paired, with Wilson and paired bootstrap intervals.
**Trade-off:** small n means wide intervals; we report them instead of overstating.

## D7. Honest impact accounting in three categories

Measured (tokens, latency, cost), estimated (FLOPs-based, low/central/high scenarios with cited assumptions), and not observable. Latency × GPU power is deliberately not used.
**Trade-off:** estimate bounds span orders of magnitude, which is less punchy but accurate.

## D8. Mock provider for development, quarantined from results

Tests and offline development use a mock provider. Every mock response is tagged `provider: mock`; the API returns `sample_data: true`; the UI shows a banner; overview and impact aggregates filter by provider. Mock numbers are never reported.

## D9. Guardrails on a public demo

Paid endpoints can require an access code; there are daily and per-workload budgets, a benchmark call cap, per-IP rate limits and payload limits. Budgets are checked before every paid call.

## D10. Simple stack

FastAPI + SQLite (WAL) for the backend, Next.js for the UI, SSE over `fetch` for the live trace (since `EventSource` cannot POST). SQLite keeps deployment to one container with a small persistent disk.
**Trade-off:** single-instance backend; fine for a demo and a benchmark of this size.
