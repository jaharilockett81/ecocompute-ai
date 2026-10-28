# Submission kit (draft)

Fill every `TBD` from the real Nebius run. Do not use mock numbers.

## Devpost

**Name:** EcoCompute AI

**Tagline:** Use the smallest NVIDIA Nemotron model that gets it right, and prove it.

### Inspiration
Most apps send every request to their biggest model because they can't tell in advance which requests a smaller one would get right. That wastes money, latency and energy on tasks a 3B-active model handles fine. We wanted a router that makes this call per task and shows its evidence.

### What it does
EcoCompute AI is an inference router for NVIDIA Nemotron models on Nebius Token Factory. For each task it:
1. analyzes the task (category, complexity, expected output size),
2. picks the start model that minimises the expected cost of the whole escalation chain while meeting a quality target,
3. calls Nebius and records provider-reported tokens, latency and cost,
4. checks the answer with deterministic validators (JSON Schema, exact fields, numeric tolerance, required terms, word limits, sandboxed unit tests),
5. repairs or escalates to a larger Nemotron only if the check fails, and
6. learns from the outcome.

Every step streams live to the UI as a machine-readable trace. A Benchmark Lab runs our 49-task EcoBench against fixed-model baselines with confidence intervals, and an Impact page separates measured cost and tokens from transparent energy, carbon and water estimates.

### Results
On the 35 held-out EcoBench tasks, versus always using Nemotron Ultra: TBD pass rate (95% CI TBD) at TBD% of the cost (95% CI TBD), with TBD% fewer tokens and TBD latency change. (Source: `benchmarks/results/run-TBD-nebius.json`.)

### How we built it
FastAPI + SQLite backend; Nebius Token Factory through its OpenAI-compatible API (retries, catalog validation, reasoning-token accounting); Beta-posterior routing policy; deterministic validators and a sandboxed Python runner; Next.js frontend with SSE live traces; Render + Vercel deployment.

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
| 0:00–0:15 | Overview | "Most apps send every request to their biggest model. EcoCompute uses the smallest Nemotron that gets it right, and proves it." |
| 0:15–1:00 | Playground, "Strict schema extraction" preset, Run | Walk the live trace: analysis, the plan table, Nano's call with real tokens and cost, the schema check, then pass or escalate. |
| 1:00–1:25 | Playground, "Multi-step reasoning", Preview then Run | "The router weighs a cheap first try against the chance of escalating." Point at P(pass) and expected cost. |
| 1:25–2:10 | Benchmark Lab, completed real run | Pass rate with CIs per condition, paired comparison vs Ultra: cost and token deltas with CIs. Mention the held-out split. |
| 2:10–2:35 | Impact | Measured vs estimated vs not observable; low/central/high bounds. |
| 2:35–2:55 | Router evidence heatmap, Methodology | "Every decision is explainable and every number is sourced." Close with the repo and license. |

## Testing instructions for judges
1. Open the app URL. The sidebar should show "backend: nebius".
2. Settings → enter the access code → Save.
3. Playground → choose a preset → Run workload.
4. Benchmark Lab → open the completed run to see full results.
