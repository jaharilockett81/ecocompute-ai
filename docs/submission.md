# Submission kit (draft)

Fill every `TBD` from the real Nebius run. Do not use mock numbers.

## Devpost

**Name:** EcoCompute AI

**Tagline:** An evidence-driven Nemotron agent that finds wasted AI compute, fixes it within hard bounds, and proves quality held.

### Inspiration
Most apps send every request to their biggest model because they can't tell in advance which requests a smaller one would get right. That wastes money, latency and energy on tasks a 3B-active model handles fine. We wanted a router that makes this call per task and shows its evidence.

### What it does
EcoCompute AI is an optimization agent for recurring LLM workloads. It runs on NVIDIA Nemotron models via Nebius Token Factory.
1. **Observe.** It runs your workload as it runs today, on the largest Nemotron, and profiles every task: pass/fail from a deterministic check, tokens, reasoning tokens, truncations, latency and cost.
2. **Reason and propose.** Nemotron reads the measured profile, diagnoses the waste, and proposes changes as structured JSON.
3. **Constrain.** Proposals may only set three knobs: which tier answers a category, an output-token cap, and escalation on validator failure. Anything else is refused before it runs.
4. **Approve, execute, measure.** You pick what to test. The candidate configuration runs on the same tasks.
5. **Verify.** A deterministic gate rejects any change where a task that passed now fails, or where cost does not fall. Regressions go back to Nemotron for a bounded number of refinement rounds.
6. **Decide.** A verified recommendation waits for you to accept, reject or export it.

A labelled safety drill proves the safeguards. It injects a shell command, which is refused by the allowlist, and a harmful 16-token cap, which is rejected by measurement. The app also includes a per-request routing Challenge, a 49-task benchmark with confidence intervals, and an Impact page that separates measured cost from estimated energy.

### Results
Optimizer on real Nebius, support-ops workload (8 tasks, one run): quality held at 7/8 with no per-task regression, inference cost −63.7% ($0.00545 → $0.00198), tokens −11.6%, estimated energy −69%. Tradeoff: summed model latency +33% (one escalation). The safety drill refused an injected shell command and rejected an injected 16-token cap (0/8 passed). Source: `benchmarks/results/optimization-b75c45c2fcc1431f-nebius.json`, `docs/TRACE.md`.
On 35 held-out EcoBench tasks versus always using Nemotron Ultra, calibrated adaptive routing passed 34/35 against 33/35, losing no task that Ultra passed, at 80.8% lower cost (95% CI −93% to −66%). The tradeoff: it was slower (median 1.6 s vs 1.1 s, p95 5.7 s vs 2.9 s), and tokens did not fall; the saving comes from cheaper models. A replicate run gave −69% to −73% cost, also with 0 tasks lost. The pass-rate difference CI includes zero, so we claim no quality loss, not a quality gain. (Source: `benchmarks/results/run-1c62f1ef2642451f-nebius.json`, `docs/BENCHMARK.md`.)

### How we built it
FastAPI + SQLite backend; Nebius Token Factory through its OpenAI-compatible API (retries, catalog validation, reasoning-token accounting); Beta-posterior routing policy; deterministic validators and a sandboxed Python runner; Next.js frontend with SSE live traces; Docker backend + Vercel frontend. A labelled safety drill corrupts a real answer on purpose to prove the gate rejects bad candidates before approval.

### Challenges
- Reasoning models emit hidden reasoning tokens, so a "small" model is not always cheap per answer. We count reasoning tokens in cost and in the router's expected-token estimates.
- Honest evaluation: we wrote an original benchmark with a calibration/test split so the warm router never sees the cases it is scored on.
- Environmental impact can't be measured through an API, so we report it as a bounded estimate with every assumption listed.

### What we learned
On real runs, Nano handled classification, coding, reasoning and data interpretation in our test set, but missed details in summaries (dropping "load balancer" or writing "Nov 20"); escalation caught those. Nano was the cheapest per call but also the slowest on this endpoint (median 6.1 s vs 1.0 s for Ultra), so cost and latency pulled in opposite directions. Strict validators also flag answers a person would accept ("Dr. Priya Raman"); we kept them strict rather than tune them after the fact.

### What's next
Learned per-customer evidence, more validators, multi-provider tiers, and a drop-in OpenAI-compatible proxy endpoint.

### Built with
nvidia-nemotron, nebius-token-factory, python, fastapi, sqlite, next.js, react, typescript, tailwind, render, vercel

### Try it
- App: TBD (access code for paid calls: in the testing instructions)
- Code: https://github.com/jaharilockett81/ecocompute-ai (MIT)
- Video: TBD

### Platform feedback (Nebius Token Factory)
The OpenAI-compatible API made the integration quick, and usage includes reasoning tokens, which matter: most Nemotron completion tokens on our tasks were reasoning (e.g. 8,441 of 10,241 for Ultra on the held-out set). The serverless endpoints expose no GPU or power telemetry, so energy has to be estimated. Per-call latency varied by model in ways we did not expect (Nano slower than Ultra on our runs).

## Demo video script (under 3 minutes)

Record against the real Nebius backend (the sidebar card must read "Nebius", not "Mock provider"). Hide the terminal and `.env`; no key may appear on screen. Numbers below are from run `b75c45c2fcc1431f` (docs/TRACE.md); if you re-run live, say the numbers the screen shows, not these.

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:20 | **Problem.** Overview hero | "Teams send every recurring AI job to their biggest model. That is wasted compute, and nobody can prove which jobs could use less. EcoCompute makes that waste measurable, correctable and independently verifiable, without giving up required quality." |
| 0:20–0:45 | **Architecture.** Methodology → section 1, then Model Router cards | "Nemotron Nano, Super and Ultra on Nebius Token Factory. Nemotron proposes; deterministic validators decide; a person signs off. The model can touch only three knobs." |
| 0:45–1:20 | **Live routing and verification.** Optimize → Support ops → Run baseline → Run Nemotron analysis → review → Approve test | "Eight real tasks on Ultra: 7 of 8 pass. Nemotron Super reads the measured profile and proposes moving classification and extraction to Super with token caps. I approve the test; the gate re-runs the same tasks and checks for any per-task regression." |
| 1:20–1:50 | **Baseline and benchmark.** Before/after card, then Benchmarks → held-out run (if completed) | "Same quality, 7 of 8, no task lost. Cost down 64 percent. But it was 33 percent slower, and we say so." Held-out run: read the paired outcomes column (gains and losses per task), not just the pass rates. If the held-out run isn't done, skip that part and don't mention it. |
| 1:50–2:15 | **Safety.** Safety drill card (labelled safety test) | "This is a safety test. We inject two bad proposals. A shell command is refused before it runs. A 16-token cap passes the schema, so we run it, and the gate rejects it: 0 of 8 pass. The LLM can never override a failing validator." |
| 2:15–2:40 | **Impact.** Impact page | "A is measured: tokens, cost, latency. B is an estimate with low, central and high bounds, never a power reading. C is what an API can't show: GPU utilisation and power. The analysis paid for itself after about two runs." |
| 2:40–2:55 | **Close.** Decision → Accept → Export, then the README | "Nothing changes until a person accepts. Open source, MIT licensed, and every number links to a provider request ID." |

## Testing instructions for judges
1. Open the app URL. The provider card at the bottom of the sidebar should read "Nebius" (if it reads "Mock provider", the backend has no key and everything is labelled sample data).
2. Settings → enter the access code → Save.
3. Optimize → pick a workload → Run baseline → Run Nemotron analysis → Approve test (a few minutes in total) → Accept or Reject → Export.
4. The Challenge → Run live on any scenario. Check the request IDs and open the raw JSON links.
5. Playground → choose a preset → Run workload.
6. Benchmark Lab → open the completed run to see full results.
