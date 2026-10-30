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
Optimizer on real Nebius: TBD (from `benchmarks/results/optimization-*-nebius.json`).
On the 35 held-out EcoBench tasks, versus always using Nemotron Ultra: TBD pass rate (95% CI TBD) at TBD% of the cost (95% CI TBD), with TBD% fewer tokens and TBD latency change. (Source: `benchmarks/results/run-TBD-nebius.json`.)

### How we built it
FastAPI + SQLite backend; Nebius Token Factory through its OpenAI-compatible API (retries, catalog validation, reasoning-token accounting); Beta-posterior routing policy; deterministic validators and a sandboxed Python runner; Next.js frontend with SSE live traces; Docker backend + Vercel frontend. A labelled safety drill corrupts a real answer on purpose to prove the gate rejects bad candidates before approval.

### Challenges
- Reasoning models emit hidden reasoning tokens, so a "small" model is not always cheap per answer. We count reasoning tokens in cost and in the router's expected-token estimates.
- Honest evaluation: we wrote an original benchmark with a calibration/test split so the warm router never sees the cases it is scored on.
- Environmental impact can't be measured through an API, so we report it as a bounded estimate with every assumption listed.

### What we learned
TBD after the real run (e.g. which categories Nano handles reliably, where Super is the sweet spot).

### What's next
Learned per-customer evidence, more validators, multi-provider tiers, and a drop-in OpenAI-compatible proxy endpoint.

### Built with
nvidia-nemotron, nebius-token-factory, python, fastapi, sqlite, next.js, react, typescript, tailwind, render, vercel

### Try it
- App: TBD (access code for paid calls: in the testing instructions)
- Code: TBD (MIT)
- Video: TBD

### Platform feedback (Nebius Token Factory)
TBD: note anything real from setup, e.g. catalog model IDs vs docs, usage fields for reasoning tokens, rate limits, latency.

## Demo video script (under 3 minutes)

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:15 | Overview | "Teams send every recurring AI job to their biggest model. EcoCompute treats that waste as a bug: it measures, lets Nemotron diagnose, and keeps only fixes that are proven safe." |
| 0:15–0:35 | Optimize → Support ops batch → Run baseline | "Eight real tasks on Nemotron Ultra via Nebius Token Factory, each with a deterministic check." Point at pass count, cost, tokens, and the "GPU not observable" note. |
| 0:35–1:05 | Run Nemotron analysis → Review | Read one finding and its cited evidence. "Nemotron can only touch three knobs. Anything else is refused before it runs." Select the proposals. |
| 1:05–1:50 | Approve test → live verification → gate | "Same tasks, candidate config." Show the gate checks. If round 1 was rejected, show the regressions going back to Nemotron and round 2. Report what actually happened. |
| 1:50–2:15 | Safety drill card | "We inject two bad proposals. A shell command: refused, never executed. A 16-token cap: allowed by the schema, so we run it, and the gate rejects it on measured regressions." |
| 2:15–2:40 | Before/after → Decision | Cost, tokens, model time, estimated energy (labelled estimate), break-even. Click Accept. Export the recommendation. |
| 2:40–2:55 | README | "Open source, MIT, reproducible with one script. Every number links to a provider request ID." |

## Testing instructions for judges
1. Open the app URL. The sidebar should show "backend: nebius".
2. Settings → enter the access code → Save.
3. Optimize → pick a workload → Run baseline → Run Nemotron analysis → Approve test (a few minutes in total) → Accept or Reject → Export.
4. The Challenge → Run live on any scenario. Check the request IDs and open the raw JSON links.
5. Playground → choose a preset → Run workload.
6. Benchmark Lab → open the completed run to see full results.
