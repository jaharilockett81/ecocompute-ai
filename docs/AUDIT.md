# Engineering audit and submission readiness (2026-10-30)

This audit separates what is implemented and tested from what depends on credentials or infrastructure. Nothing here claims a result that has not been run.

## Grand-prize audit (2026-10-30, skeptical-judge pass)

Scored on the evidence in this repository today, not on what it might become. These are not predictions of the outcome.

| Criterion | Score | Strongest evidence | Largest weakness | Single best improvement |
| --- | --- | --- | --- | --- |
| Technological implementation | **4** | Real Nebius runs with request IDs; deterministic validators, bounded escalation, allowlisted agent actions, independent gate, budgets and rate limits; 68 tests; offline verifier (`scripts/verify_benchmark.py`) PASS | No public deployment yet; the agent loop has one real workload run | A public URL that runs a real call end to end |
| Design | **4** | One coherent system across 10 screens, light and dark, AA contrast, phone width, every state (empty, loading, error, sample data) labelled | Dense tables on the Benchmark page; judges must read to get the point | A video that shows the three numbers (cost, losses, latency) before any table |
| Potential impact | **4** | Held-out: −81% cost [−93, −66], 0 of 35 tasks lost, replicated (−69 to −73%) | Latency is worse (+62–72% mean); 35 tasks from one team-authored dataset; prices are configured, not billed | Fixed Nano/Super on the same held-out tasks, so the gain over "just use a cheaper model" is measured, not argued |
| Quality of idea | **3–4** | Validator-triggered escalation plus a Nemotron analyst that can only propose bounded, measured, human-approved changes | Model cascades and LLM routers already exist (e.g. FrugalGPT-style cascades, commercial routers). The novelty is the verification and evidence layer, not routing itself | Say this plainly in the README and video, and show the gate rejecting a bad change |

### Objections a skeptical judge will raise

| Objection | Answer, with evidence | Residual risk |
| --- | --- | --- |
| "An attractive LLM wrapper." | Routing, validation, escalation, the gate and the budget are deterministic code (`router/engine.py`, `evaluation/`, `optimizer.gate`), tested without a network. Nemotron does the work and proposes changes, but cannot accept them. | Low |
| "Is NVIDIA central?" | The method relies on a model family with a cost-capability ladder: Nano, Super and Ultra are the three rungs, and all inference ran on them via Nebius. | Low |
| "Are the benchmarks defensible?" | Calibration and held-out splits are disjoint and leakage is checked by script. Results come with Wilson CIs, paired bootstrap CIs, per-task gains and losses, every failure, a replicate run, and the observed temperature-0 non-determinism. | Medium: n=35, one dataset, authored by us |
| "Could a simpler baseline do the same?" | On calibration, always-Super lost nothing at −76% cost. On the held-out set, one task (sum-03) failed on both Nano and Super and passed only after escalation to Ultra, which a fixed cheaper model can't do. The matched held-out run of fixed Nano/Super is **pending**. | **High until that run lands** |
| "Environmental savings overstated?" | Energy is category B: a FLOPs estimate with low/central/high bounds, labelled "estimate, not a measurement". GPU power is category C, not observable. Savings claims use measured cost only. | Low |
| "Reliable?" | Retries with backoff, timeouts, a daily budget, per-workload budget, call caps, and runs marked interrupted on restart; 68 tests. | Medium: not yet load-tested on a public host |
| "Can judges inspect the evidence?" | Bundles are committed, with every call, token count, request ID and validator verdict. The hosted app imports them at startup. The verifier needs no key. | Low |
| "Accessible?" | Text contrast ≥ 5:1 in both themes, visible focus rings, labelled controls, reduced-motion support. | Low–medium: no screen-reader pass |
| "Is the demo convincing?" | The script answers the five questions with measured numbers and shows a live call, the gate and the safety drill. | High until the URL and video exist |

### Eligibility and submission checklist

| Item | Status |
| --- | --- |
| Uses NVIDIA Nemotron via Nebius Token Factory | ☑ verified live (verify_nebius PASS; all benchmark calls report Nemotron model IDs and provider nebius) |
| Public code repository, open-source license | ☑ github.com/jaharilockett81/ecocompute-ai, MIT |
| Working public demo URL | ☐ waiting on the Render + Vercel deploy |
| Video under 3 minutes, public | ☐ script and recording plan ready in docs/submission.md |
| Devpost text | ◐ written from real results; app and video links missing |
| Testing instructions plus judge access code | ◐ instructions written; the code is set when deploying |
| No secrets in repo, logs or screenshots | ☑ the key is read from the environment only; the API exposes only `api_key_configured: true/false`; redaction tested |

## 0. Final upgrade pass (design, Benchmark Lab, submission)

| Change | Evidence |
| --- | --- |
| Approved design system: ivory/forest light theme, evergreen/mint dark theme, Newsreader editorial headings, pill controls, reduced-motion aware fades | `globals.css`, `layout.tsx`. Every text token measured ≥ 5:1 contrast (WCAG AA) on its background in both themes; no horizontal scroll at 390 px on any of the 10 pages (headless check) |
| Overview: editorial hero, tier map, latest verified Nebius run pulled from the API (nothing hard-coded) | `src/app/page.tsx` |
| Model Router: model cards with routing roles ("lower-cost", "intermediate", "highest capability · escalation"), stated as roles, not performance guarantees | `src/app/router/page.tsx` |
| Benchmark Lab: $/task, median and p95 latency (p95 hidden below n=20), per-task paired outcomes (both pass / both fail / gained / lost, with case IDs), a quality-failures list per condition, and a warning when a run isn't on the held-out split | `backend/app/benchmark/metrics.py`, `benchmarks/[id]/page.tsx`, `benchmarks/page.tsx`; new test for losses hidden behind equal pass rates |
| Impact: A measured / B estimate (dashed, "estimate, not a measurement") / C not observable; the fixed-vs-adaptive comparison appears only when a completed run has both conditions on the same tasks | `src/app/impact/page.tsx` |
| History: server-side search (task text, case ID, category, workload ID) with parameterized, wildcard-escaped LIKE, plus source and status filters | `store.list_workloads`, new API test incl. `%` and `' OR 1=1 --` |
| Methodology: editorial, expandable sections, new "optimization loop" section and A/B/C explainer | `methodology/page.tsx` |
| Settings: secure-configuration indicators (key set or not, never its value), daily spend meter, cost limits, analyst/judge models, diagnostics | `settings/page.tsx` |
| Demo script rewritten to the seven-part video structure with the real run's numbers | `docs/submission.md` |

Tests: 68 backend tests pass; `tsc` and `next build` pass. No backend logic was changed for appearance; the two backend changes (paired outcomes, history search) add data the UI needed.

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

- `cd backend && python -m pytest -v`: **68 passed** ([full output](TEST_OUTPUT.txt)).
- `cd frontend && npx tsc --noEmit && npm run build`: passes.
- The full `/optimize` journey was driven in a headless browser against the mock provider (select → baseline → analysis → approve → verify with drill → decision), with no console errors.
- `scripts/run_optimizer.py` was run on the mock provider. The output is sample data and is not reported anywhere as a result.
- **Real benchmarks:** calibration + two held-out runs on Nebius, see [BENCHMARK.md](BENCHMARK.md).

## 4. Remaining limitations

- The hosted demo and the YouTube video do not exist yet.
- Adaptive routing is slower than always-Ultra on the held-out set (mean +62–72%, p95 about 2×).
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
| Reproducible baseline vs optimized benchmark | ☑ optimizer workload + held-out benchmark (2 runs) | docs/BENCHMARK.md; optional: `run_optimizer.py data-pipeline`, `mixed-agent` |
| Deliberate failure/rejection scenario | ☑ | Optimizer drill + Challenge drill (tested) |
| Passing tests with output | ☑ | `docs/TEST_OUTPUT.txt` |
| Public repo, license, setup instructions | ☑ | — |
| Functioning hosted demo | ☐ | Deploy the backend (Render/HF Spaces) + frontend (Vercel) |
| Public YouTube video < 3 min | ☐ | Record from the script in `docs/submission.md` |
| Judge-facing README for all four criteria | ☑ | Fill the Live demo / Video links and the Results rows |
| Devpost copy | ◐ results filled | App URL and video link |

## 6. Suggested scores today (1–5), with evidence

These are scores for the repository as it stands now, not for what it would be after the real runs.

| Criterion | Now | After real runs + deploy | Why |
| --- | --- | --- | --- |
| Technological implementation | **4** (was 3 before the live run) | 5 | The loop is complete and tested: structured output, allowlist, independent gate, bounded refinement, retries, timeouts, budgets, sandboxed code checks, human approval, and 66 passing tests. Now verified live: verify_nebius PASS and a real optimizer run (docs/TRACE.md). What's missing for a 5 is the hosted demo. |
| Design | **4–5** | 5 | Every screen now follows the approved design, checked in light, dark and at phone width, with AA contrast. The seven-step journey handles every state. Not yet seen on a hosted URL. |
| Potential impact | **4** (held-out: −81% cost, 0 of 35 tasks lost, replicated; latency worse) | 4–5 | Clear audience, cost/tokens/latency/CPU/calls/energy-estimate reporting and break-even, honest limits. But no real savings number exists yet, and n=8 per workload is small. |
| Quality of the idea | **4** | 4–5 | The separation of powers (the model proposes, deterministic measurement decides, a human signs off) on real workloads is distinct from profilers, linters, code assistants and routers, and it is visible in the implementation. The EcoGuard comparison is missing. |

The fastest way to raise all four scores: put the key on a reachable host, run `verify_nebius.py` and one `run_optimizer.py`, commit the bundle, deploy, and record the video.
