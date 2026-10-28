# EcoCompute AI — STATUS (handoff, 2026-10-27 05:55 ET)

Deadline: **Oct 30, 2026, 10:00 AM PT / 1:00 PM ET** — Best Apps & Agents track.

## Done (backend, `backend/`)
- Config from env; Nebius Token Factory adapter (`providers/nebius.py`): bearer auth, `/models` catalog check, retries w/ backoff on 429/5xx/timeout, latency, provider-reported tokens incl. reasoning tokens, `<think>` stripping, secret redaction.
- Mock provider for offline dev/tests — every response tagged `provider: mock`, API returns `sample_data: true`.
- `EcoComputeRouter` (`router/engine.py`): Analyze → Select → Execute → Evaluate → Repair/Escalate → Record → Learn, with streamed machine-readable trace.
- Policy (`router/policy.py`): Beta-posterior pass probabilities (heuristic prior + observed evidence), picks start tier minimising expected escalation-chain cost subject to quality threshold, budget, latency, and a 0.5 first-attempt pass floor.
- Validators: JSON schema, field equality, exact/label/numeric/regex, word/bullet limits, sandboxed Python tests. Optional model judge labelled as estimate, cost counted as overhead.
- Guardrails: daily budget, per-workload budget, call cap for benchmarks, rate limit, access code for paid endpoints, payload limits.
- Benchmark: `benchmarks/datasets/ecobench-v1.json` — 49 original cases, 7 categories, 14 calib / 35 held-out test. Conditions `fixed:<tier>`, `adaptive` (cold), `adaptive_warm` (calibration evidence only — no test leakage). Wilson CIs, paired bootstrap CIs, JSON export.
- `EnvironmentalImpactEstimator`: Category A measured / B FLOPs-based low-central-high scenarios / C not observable, cited assumptions.
- FastAPI endpoints: health, config, diagnostics, models, presets, workloads (+SSE stream), history, router preview/evidence, benchmarks (create/progress/cancel/results), impact, overview.
- Scripts: `scripts/verify_nebius.py` (Acceptance Test 1), `scripts/run_benchmark.py`.

## Tests
- `cd backend && python -m pytest -q` → **44 passed** (mock provider + simulated HTTP). Covers acceptance tests 2–8 (backend parts).
- **Test 1 (real Nebius call): NOT yet verified** — no API key in the build sandbox and its proxy blocks api.tokenfactory.nebius.com.

## Known issues / to verify
- Model IDs and prices come from third-party catalogs → confirm with `verify_nebius.py`.
- Nemotron reasoning tokens may hit `max_output_tokens` (2048) → watch `finish_reason=length`.
- Test suite writes mock result files into benchmarks/results (gitignored); point RESULTS_DIR at a temp dir in tests.
- Mock benchmark numbers are meaningless placeholders (mock answers don't match checks); never use them in the submission.

## Remaining (priority order)
1. Run `python scripts/verify_nebius.py` with a real key; fix model IDs.
2. Run calib then test benchmark with real Nebius (est. total < $1 at listed prices).
3. Next.js frontend (Overview, Playground w/ live trace, Router, Benchmark Lab, Impact, History, Methodology, Settings) — **not started**.
4. README, docs/methodology.md, DECISIONS.md, LICENSE (MIT).
5. Deploy backend (e.g. Render/Fly/Nebius Serverless) + frontend (Vercel); set access code; smoke-test hosted URL.
6. Public GitHub repo with license visible; <3 min YouTube demo; Devpost copy + platform feedback.
7. Optional: Tavily evidence agent (Best Use of Tavily bonus).
