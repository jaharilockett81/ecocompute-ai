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

## Demo video (under 3 minutes): script and recording plan

The script answers the five questions in order. Every number is from a committed Nebius bundle. If you run something live during recording, read what the screen shows instead.

| Time | Question | Show | Say |
| --- | --- | --- | --- |
| 0:00–0:20 | **1. The problem** | Overview hero | "Most teams send every AI request to their biggest model, because nobody can tell in advance which requests a smaller model would get right. On our held-out tasks, that habit cost five times more than it needed to." |
| 0:20–0:45 | **2. Why existing options fall short** | Model Router cards, then the Benchmarks calibration run | "Just picking a cheaper model is a guess. On calibration, Nano was 94 percent cheaper but lost tasks, and Super was safe but still four times Nano's price. Profilers show cost but not quality. Routers pick a model but can't prove they didn't break anything." |
| 0:45–1:20 | **3. What's new** | Methodology section 1, then Playground: run one preset live and show the trace (start tier, validator verdict, escalation) | "EcoCompute keeps a Bayesian estimate of whether each Nemotron model passes each kind of task. It starts on the cheapest model likely to pass, checks the answer with a deterministic validator, and escalates only when the check fails. For recurring jobs, Nemotron Super acts as the analyst, but it can only touch three knobs, and a gate re-runs the tasks before a person approves anything." |
| 1:20–1:55 | **4. What the experiments showed** | Benchmarks → run 1c62f1ef: results table, paired comparison, quality failures | "35 held-out tasks that the router never saw. Always-Ultra passed 33. Adaptive routing passed 34, lost none of Ultra's tasks, and cost 81 percent less, with a 95 percent interval of 66 to 93. A second run gave 69 to 73 percent. The tradeoff: it's slower, with median 1.6 seconds instead of 1.1, because Nano is slow per call here and escalations add calls. Tokens didn't fall; the saving comes from price." |
| 1:55–2:20 | **Safety** | Optimize → safety drill card (labelled safety test) | "This is a safety test. We inject a shell command: it's refused before it runs. We inject a 16-token cap: it's allowed by the schema, so we run it, and the gate rejects it because 0 of 8 tasks pass. The language model can never override a failing validator." |
| 2:20–2:45 | **5. Why it matters** | Impact page: A measured, B estimate with bounds, C not observable | "For NVIDIA and Nebius customers, this turns a model family into a cost curve you can safely move along. Cost and tokens are measured. Energy is an estimate with low and high bounds, never a power reading. GPU power isn't observable through an API, and we say so." |
| 2:45–2:58 | Close | README, verify_benchmark.py PASS in a terminal | "Open source, MIT. Every number traces to a provider request ID, and one offline script re-checks the evidence." |

When the fixed Nano and Super held-out run is in, replace the 0:20–0:45 calibration numbers with the held-out ones (docs/BENCHMARK.md).

### Recording plan

1. **Before recording.** Open the public backend URL `/health` once to wake the free Render instance (cold start is about a minute). Enter the access code in Settings. Close other tabs. Hide the bookmarks bar.
2. **Screen.** Use a browser window around 1440×900 with zoom at 110–125% so table text is readable on YouTube at 1080p. Record in light mode, with one 3-second cut to dark mode on the Overview.
3. **Capture.** Use QuickTime (File → New Screen Recording) or OBS at 1080p, 30 fps. Record each row as its own clip, so a mistake costs one clip, not the whole take.
4. **Narration.** Record the voice separately from the script above, then lay it over the clips in iMovie or CapCut. Aim for about 150 words a minute. The script is about 420 words, so it fits in 2:55.
5. **Live call.** The Playground run in row 3 is the live Nebius inference. Use the "Routine classification" preset; it costs a fraction of a cent.
6. **Secrets.** Never show `.env`, the Render environment page, or a terminal holding the key. The access code may appear only if it's the judge code in the testing instructions.
7. **Upload.** Upload to YouTube as Public or Unlisted with the title "EcoCompute AI: evidence-driven routing for NVIDIA Nemotron on Nebius". Paste the link into Devpost and the README.

## Testing instructions for judges
1. Open the app URL. The provider card at the bottom of the sidebar should read "Nebius" (if it reads "Mock provider", the backend has no key and everything is labelled sample data).
2. Settings → enter the access code → Save.
3. Optimize → pick a workload → Run baseline → Run Nemotron analysis → Approve test (a few minutes in total) → Accept or Reject → Export.
4. The Challenge → Run live on any scenario. Check the request IDs and open the raw JSON links.
5. Playground → choose a preset → Run workload.
6. Benchmark Lab → open the completed run to see full results.
