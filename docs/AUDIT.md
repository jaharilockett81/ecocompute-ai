# Engineering audit and submission readiness (2026-10-30)

This audit separates what is implemented and tested from what depends on credentials or infrastructure. Nothing here claims a result that has not been run.

## 1. What changed in the final pass

| Change | Files |
| --- | --- |
| **Optimizer agent**: observe → reason → propose → approve → execute → measure → verify → refine → decide | `backend/app/optimizer.py` (new) |
| Nemotron analyst: JSON-mode call, schema validation, fallback when JSON mode is unsupported, configurable model (`NEBIUS_ANALYST_MODEL`, default Nemotron Super) | `optimizer.py`, `backend/app/core/config.py` |
| Allowlist of three knobs; unknown actions refused before execution | `optimizer.validate_proposal` |
| Independent gate: per-task no-regression, pass count, provider errors, lower cost | `optimizer.gate` |
| Bounded refinement (1–3 rounds) with measured regressions fed back to Nemotron | `Optimizer.verify` |
| Safety drill: injected `execute_command` (refused) and 16-token cap (executed, rejected by measurement) | `optimizer.drill_proposals` |
| Human approval before testing, plus accept/reject/export after verification | `Optimizer.decide`, `/api/optimize/*` |
| Measurements: backend CPU time, wall time, calls, energy estimate, break-even runs; GPU marked not observable | `optimizer.execute` |
| Upload of user workloads (EcoBench case format, deterministic checks required) | `optimizer.validate_upload` |
| Persistence and evidence bundles for optimizations | `backend/app/persistence/store.py`, `bundles.py` |
| API: `/api/optimize/workloads`, `/sessions`, `/sessions/{id}/baseline|analyze|verify` (SSE), `/decision`, `/export` | `backend/app/main.py` |
| CLI: `scripts/run_optimizer.py` | new |
| UI: `/optimize`, a seven-step journey with loading, empty, error and success states; nav entry; Overview call to action | `frontend/src/app/optimize/page.tsx`, `Nav.tsx`, `page.tsx`, `lib/api.ts` |
| Mock provider: honours output caps, scripted analyst, reference answers for EcoBench (sample data only) | `backend/app/providers/mock.py`, `factory.py` |
| Bug fix: an empty `NEBIUS_JUDGE_MODEL` / `NEBIUS_ROUTER_MODEL` in `.env` produced an empty model ID | `config.py` |
| Earlier today: Challenge safety drill (injected candidate rejected) and the explicit `approve` step in the router | `challenge.py`, `router/engine.py`, `evaluation/faults.py` |
| Tests: 9 optimizer tests (66 total) | `backend/tests/test_optimizer.py` |
| Docs: judge-facing README, results, this audit, demo script, test output | `README.md`, `docs/*` |

## 2. Real integration verification

**Update 2026-10-30: `scripts/verify_nebius.py` passed on the author's machine** ("PASS — genuine Nebius inference verified"; e.g. Nemotron Ultra, request `chatcmpl-bc04339055083597`). Originally: this build environment's network proxy blocks `api.tokenfactory.nebius.com`, so no live Nebius call has been made from here. The Nebius client is unit-tested with mocked HTTP. The model IDs in `.env.example` are unverified until `python scripts/verify_nebius.py` runs with a real key. This is the single most important open item.

## 3. Tests and benchmarks actually run

- `cd backend && python -m pytest -v`: **66 passed** ([full output](TEST_OUTPUT.txt)).
- `cd frontend && npx tsc --noEmit && npm run build`: passes.
- The full `/optimize` journey was driven in a headless browser against the mock provider (select → baseline → analysis → approve → verify with drill → decision), with no console errors.
- `scripts/run_optimizer.py` was run on the mock provider. The output is sample data and is not reported anywhere as a result.
- **Real benchmarks:** none yet (see 2).

## 4. Remaining limitations

- No live Nebius evidence yet; the hosted demo and the YouTube video do not exist yet.
- An accepted recommendation is exported, not applied to the live Playground router. That is deliberate for safety, but it means "apply" is a manual step.
- Each optimizer run uses 8 tasks once per configuration: enough to show per-task regressions, not enough for statistical claims. The 35-task benchmark carries the CIs.
- The optimizer verifies on the same workload it tunes on (intended for recurring jobs, stated in the UI and README).
- GPU utilisation, GPU memory and electrical power are not observable through Token Factory; energy is an estimate.
- Differentiation from your earlier EcoGuard PlanetOps project is **not written yet**, because its contents aren't in this repo. Add one line to the README "What is new here" table.

## 5. Submission readiness checklist

| Item | Status | Needs |
| --- | --- | --- |
| Real Nebius Token Factory call + verified Nemotron IDs | ☑ | verify_nebius.py PASS, 2026-10-30 |
| NVIDIA open model used | ☑ verified live | Nemotron via Token Factory |
| Architecture diagram | ☑ | README |
| One complete end-to-end optimization trace | ☑ real | docs/TRACE.md + committed nebius bundle |
| Reproducible baseline vs optimized benchmark | ☑ one real workload / ☐ more workloads + held-out benchmark | `run_optimizer.py data-pipeline`, `mixed-agent`; `run_benchmark.py` |
| Deliberate failure/rejection scenario | ☑ | Optimizer drill + Challenge drill (tested) |
| Passing tests with output | ☑ | `docs/TEST_OUTPUT.txt` |
| Public repo, license, setup instructions | ☑ | — |
| Functioning hosted demo | ☐ | Deploy the backend (Render/HF Spaces) + frontend (Vercel) |
| Public YouTube video < 3 min | ☐ | Record from the script in `docs/submission.md` |
| Judge-facing README for all four criteria | ☑ | Fill the Live demo / Video links and the Results rows |
| Devpost copy | ◐ | Fill the TBDs from real bundles only |

## 6. Suggested scores today (1–5), with evidence

These are scores for the repository as it stands now, not for what it would be after the real runs.

| Criterion | Now | After real runs + deploy | Why |
| --- | --- | --- | --- |
| Technological implementation | **4** (was 3 before the live run) | 5 | The loop is complete and tested: structured output, allowlist, independent gate, bounded refinement, retries, timeouts, budgets, sandboxed code checks, human approval, and 66 passing tests. Now verified live: verify_nebius PASS and a real optimizer run (docs/TRACE.md). What's missing for a 5 is the hosted demo. |
| Design | **4** | 4–5 | A coherent seven-step journey with every state handled, light and dark themes, before/after pairs on a shared scale, and drill and gate cards. Not yet seen with real data or on a hosted URL. |
| Potential impact | **3–4** (one real run: −64% cost at equal quality, +33% latency) | 4 | Clear audience, cost/tokens/latency/CPU/calls/energy-estimate reporting and break-even, honest limits. But no real savings number exists yet, and n=8 per workload is small. |
| Quality of the idea | **4** | 4–5 | The separation of powers (the model proposes, deterministic measurement decides, a human signs off) on real workloads is distinct from profilers, linters, code assistants and routers, and it is visible in the implementation. The EcoGuard comparison is missing. |

The fastest way to raise all four scores: put the key on a reachable host, run `verify_nebius.py` and one `run_optimizer.py`, commit the bundle, deploy, and record the video.
