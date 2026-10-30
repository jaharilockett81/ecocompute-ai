# Engineering audit (2026-10-30)

An honest audit of this repository against the hackathon's requirements and judging criteria. It separates what is implemented and tested from what is planned, and from what has only ever run against the offline mock provider.

## A. What exists today

| Capability | State | Evidence |
| --- | --- | --- |
| Nebius Token Factory client (OpenAI-compatible) with timeouts, bounded retries (429/5xx/timeout, backoff + jitter), non-retryable 4xx, catalog check | Implemented and unit-tested. **Not yet exercised against the live API from this repo's CI or sandbox** (outbound access to Nebius is blocked there). | `backend/app/providers/nebius.py`, `backend/tests/` |
| Three NVIDIA Nemotron tiers (Nano / Super / Ultra) | Configured. **Model IDs are unverified** until `scripts/verify_nebius.py` runs with a real key. | `.env.example`, `backend/app/core/config.py` |
| Router agent: analyze → select → execute → evaluate → repair/escalate → approve → record → learn | Implemented, tested with deterministic fixtures. | `backend/app/router/engine.py` |
| Deterministic verification gate before an answer is approved | Implemented. An answer is released (`approve` trace step) only after the validators pass; a failing answer is never approved. | `engine.py`, `test_failed_gate_is_never_approved` |
| Validators: JSON Schema, exact fields, exact/label/numeric/regex, required terms, word/bullet limits, Python unit tests | Implemented. Python tests run in a subprocess with an empty environment and a wall-clock timeout. | `backend/app/evaluation/` |
| **Safety drill: intentionally failing candidate is rejected** | Implemented today. The first real answer in the EcoCompute lane is corrupted on purpose (labelled `INJECTED` in the trace, the attempt record, the API and the UI), the gate rejects it, the router escalates and re-checks against the same requirement. Injected attempts are excluded from routing evidence. If the gate ever accepts the injected answer, the run is marked as a gate defect and nothing is released. | `backend/app/evaluation/faults.py`, `fault_drill` scenario, 3 new tests |
| EcoCompute Challenge: routed lane vs fixed-baseline lane on the same task, concurrent, with overhead accounting | Implemented. Runs end to end on the mock provider; **no real Nebius run recorded yet**. | `backend/app/challenge.py`, `/challenge` page, `scripts/run_challenge.py` |
| EcoBench v1 benchmark (49 tasks, 14 calibration / 35 held-out), Wilson CIs, paired bootstrap | Implemented. **No real Nebius run recorded yet**, so the README has no results table. | `backend/app/benchmark/`, `benchmarks/datasets/` |
| Impact: measured (tokens, cost, latency) / estimated (energy, CO₂e, water with low/central/high) / not observable | Implemented. Energy is an **estimate from FLOPs**, never a power measurement. | `backend/app/sustainability/`, `docs/methodology.md` |
| Persistence of real results on a host without a disk | Implemented: result bundles exported on completion, re-imported at startup (real provider only). | `backend/app/persistence/bundles.py` |
| Guardrails for paid actions | Demo access code on every paid endpoint, per-IP rate limit, per-workload and daily budget caps checked before every call. | `backend/app/main.py`, `engine.py` |
| Mock provider | Offline, clearly labelled `sample_data: true` and with a banner on every page. Never used for reported numbers. | `backend/app/providers/mock.py` |
| Frontend (Next.js) | Implemented: Challenge, Overview, Playground, Router, Benchmarks, Impact, History, Methodology, Settings. | `frontend/` |
| Public repo, MIT license, README | Done. | GitHub, `LICENSE` |
| Hosted demo | **Not deployed yet** (needs the owner's Render/Hugging Face + Vercel accounts). | — |
| Demo video | **Not recorded yet.** Script in `docs/submission.md`. | — |

## B. Gaps ranked

**P0: eligibility and the working demo.**

1. One real Nebius Token Factory call, with the NVIDIA model IDs verified against the authenticated catalog (`scripts/verify_nebius.py`). *Blocked here; needs the key on the deployed backend or a local machine.*
2. A hosted, functional demo (backend + frontend) with the access code set.
3. A real Challenge run of each scenario, including the safety drill. Commit the `challenge-*-nebius.json` bundles.
4. A public YouTube video under 3 minutes.
5. The rejected failing candidate, plus approval only after verification. **Done in this pass.**
6. Documentation of the exact models and Nebius services used. **Done in this pass** (README "Models and services").

**P1: evidence quality.**

7. A real calibration + held-out benchmark run, with the README results table filled from the bundle.
8. Devpost copy with every TBD filled from real runs only.

**P2: polish, only after P0/P1.**

9. An optional web-search agent (Tavily). Deliberately not started: it would expand scope before eligibility is secure.
10. A drop-in OpenAI-compatible proxy endpoint, and per-customer evidence.

## G. Judging criteria audit

The track targeted is Coding & Agentic Engineering. It fits because the core of the project is an autonomous, bounded optimization agent with a deterministic verification gate between the model's proposal and its release.

| Criterion | Where it is met | Risk |
| --- | --- | --- |
| Uses Nebius Token Factory | All inference goes through `NebiusProvider` | No recorded real call yet (P0-1) |
| Uses an NVIDIA open model | Nemotron 3 Nano / Super / Ultra tiers | IDs unverified (P0-1) |
| Agentic: reasoning, tool use, observation, adaptation | Router plans a chain, observes validator results, escalates, updates Beta posteriors | — |
| Verification before consequential action | `evaluate` → `approve` gate; safety drill proves rejection on live traffic | — |
| Failure handling | Timeouts, bounded retries, provider-error escalation, budget guardrail, gate-defect detection | — |
| Fair, repeatable baseline | Same task and same requirement on the fixed large model; prior-only routing; temperature 0; held-out split | Real numbers pending (P1-7) |
| Honest measurement | Measured vs estimated vs not observable; CIs; no mock numbers in docs | — |
| Polished UX | Light/dark dashboard, live two-lane trace, "verify it yourself" call log | — |
| Reproducible without secrets | `.env.example`, Docker, CLI scripts; key only via env | — |
| Public repo, license, README, demo, video | Repo, MIT and README are done | Demo and video pending (P0-2, P0-4) |

## H. Status

**Works and is tested (57 backend tests, deterministic fixtures):** routing, validators, sandboxed code checks, repair/escalation, the approval gate, the safety drill (rejection, recovery, evidence exclusion, determinism of the corruption), Challenge comparison and verdicts, SSE streaming endpoints, the benchmark runner and statistics, bundle export/import, impact estimates. The frontend type-checks and builds. The Challenge drill was exercised end to end in a browser against the mock provider.

**Implemented but never run against real Nebius:** everything that calls the provider. With the mock provider, every number is sample data.

**Incomplete:** real Nebius verification, hosted deployment, real Challenge and benchmark results, YouTube video, filled Devpost copy.
