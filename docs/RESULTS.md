# Results

**Status (2026-10-30): live Nebius inference verified (see below); optimizer and benchmark results not recorded yet.** This file reports only what has actually been run. Rows marked *pending* are filled from committed `benchmarks/results/*-nebius.json` bundles, never by hand and never from the mock provider.

## What has been verified

| Check | How | Result |
| --- | --- | --- |
| Optimizer loop, router, validators, approval gate, escalation, safety drills, comparison logic | `cd backend && pytest -q` (deterministic fixtures, no network) | 66 passed ([output](TEST_OUTPUT.txt)) |
| Optimizer end to end (UI + API + CLI), including allowlist refusal, gate rejection of the injected 16-token cap, and accept/reject/export | Mock provider, in a browser and via `scripts/run_optimizer.py` | Runs and is labelled sample data. The mock numbers are **not** results. |
| Frontend | `npx tsc --noEmit && npm run build` | passes |
| Challenge end to end (UI + API + CLI), including the safety drill | Mock provider, in a browser and via `scripts/run_challenge.py` | Runs and is labelled sample data. The mock numbers are **not** results. |
| Nebius catalog + model IDs | `python scripts/verify_nebius.py`, run by the author on a laptop, 2026-10-30 | **PASS: genuine Nebius inference verified.** Example from the run: `nvidia/Nemotron-3-Ultra-550b-a55b` answered (model reported = model requested), 37 prompt / 166 completion (158 reasoning) tokens, 1027.5 ms, request `chatcmpl-bc04339055083597`. |

## Optimizer (real Nebius)

| Workload | Baseline (pass, cost, tokens) | Accepted round | Optimized (pass, cost, tokens) | Δ cost | Δ model time | Drill rejected? | Bundle |
| --- | --- | --- | --- | --- | --- | --- | --- |
| support-ops (8 tasks) | *pending* | | | | | | |
| data-pipeline (8 tasks) | *pending* | | | | | | |
| mixed-agent (8 tasks) | *pending* | | | | | | |

Reproduce: `python scripts/run_optimizer.py <workload>` with `NEBIUS_API_KEY` set. The script writes `benchmarks/results/optimization-<id>-nebius.json`, which contains every task, call, request ID, the analyst's raw proposals, the allowlist verdicts, each gate check and the drill. Hardware: Nebius Token Factory serverless endpoints; the provider does not disclose or expose the GPU type or utilisation. Backend CPU time is measured on whatever host runs EcoCompute.

## EcoCompute Challenge (real Nebius)

| Scenario | EcoCompute path | Requirement met (Eco / baseline) | Tokens Δ | Cost Δ | Latency Δ | Bundle |
| --- | --- | --- | --- | --- | --- | --- |
| Routine triage | *pending* | | | | | |
| Demanding extraction | *pending* | | | | | |
| Safety drill (injected fault) | *pending* | | n/a: not a performance comparison | | | |

Reproduce: `python scripts/run_challenge.py routine|demanding|fault_drill` with `NEBIUS_API_KEY` set. Each run writes `challenge-<id>-nebius.json` with every call's model, request ID, tokens, latency, validator verdict and the full trace.

## EcoBench v1 held-out test split (35 tasks, real Nebius)

| Condition | Pass rate (95% Wilson CI) | Cost / success | Tokens / task | Mean latency | Escalation rate |
| --- | --- | --- | --- | --- | --- |
| fixed:large (baseline) | *pending* | | | | |
| fixed:medium | *pending* | | | | |
| fixed:small | *pending* | | | | |
| adaptive (prior only) | *pending* | | | | |
| adaptive_warm (calibration evidence) | *pending* | | | | |

Reproduce:

```bash
python scripts/run_benchmark.py --split calib --conditions fixed:small fixed:medium fixed:large   # routing evidence only
python scripts/run_benchmark.py --split test --conditions fixed:large fixed:medium fixed:small adaptive adaptive_warm   # held-out, reported
```

## Methodology and limitations

- **Baseline:** the same tasks with the same validators on a fixed model (Nemotron Ultra by default), no escalation. Temperature 0. The Challenge uses prior-only routing so earlier traffic cannot bias it.
- **Cost** is the provider-reported tokens multiplied by the configured per-token price. Calls without usage are counted, never guessed. Reasoning tokens are included.
- **Latency** is the wall-clock time of each HTTP call as measured by the backend, plus end-to-end lane time.
- **Overhead:** routing is rule-based and evaluation is deterministic, so neither makes a paid call. Their local compute time is measured from trace timestamps.
- **Energy, CO₂e and water are estimates** from FLOPs ≈ 2 × active parameters × tokens with low/central/high assumptions. They are not power measurements: an API exposes no hardware telemetry.
- **Sample size:** 35 held-out tasks give wide confidence intervals. A CI that crosses zero is reported as "not distinguishable".
- **Safety drill** results show that the gate rejects a known-bad candidate. They are excluded from routing evidence and from any savings claim.
