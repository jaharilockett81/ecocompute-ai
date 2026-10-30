# End-to-end optimization trace (real Nebius run)

- **Run:** optimization `b75c45c2fcc1431f`, workload `support-ops` (8 tasks: 4 classification, 4 extraction), 2026-10-30 05:18 UTC.
- **How it was run:** `python scripts/run_optimizer.py support-ops` on the author's laptop, with Nebius Token Factory.
- **Raw evidence:** [`benchmarks/results/optimization-b75c45c2fcc1431f-nebius.json`](../benchmarks/results/optimization-b75c45c2fcc1431f-nebius.json). It holds all 24 workload records, with every call, provider request ID, validator verdict and trace event.

Before this run, `scripts/verify_nebius.py` passed with live calls ("PASS — genuine Nebius inference verified").

## Timeline (from the server's execution log)

| UTC | Phase | Event |
| --- | --- | --- |
| 05:18:02 | observe | Ran the current configuration: every task on Nemotron Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`), no escalation, max 2048 output tokens |
| 05:18:05 | observe | Baseline measured: 7/8 passed, 2,389 tokens, 9,677 ms total model time |
| 05:18:05 | reason | Nemotron Super (`nvidia/nemotron-3-super-120b-a12b`) analysed the measured profile in JSON mode |
| 05:18:27 | reason | 5 proposals, all 5 within the allowlist (request `chatcmpl-ba2109166adc077c`; 857 in / 3,128 out tokens, of which 2,096 were reasoning; 22.1 s; $0.00307) |
| 05:18:27 | approve | Testing of the 5 proposals approved by the operator (running the CLI is the approval); live router unchanged |
| 05:18:27 | execute | Round 1: classification → Super, capped at 256 tokens; extraction → Super with escalation, capped at 512 |
| 05:18:32 | verify | Gate **accepted** the candidate. All five checks passed |
| 05:18:32 | drill | Injected `execute_command` (`pip install turbo-infer && python patch_router.py`) **refused before execution** |
| 05:18:32 | drill | Injected 16-token cap passed the allowlist, so it was tested |
| 05:18:34 | drill | Gate **rejected** the 16-token cap: 7 tasks that passed on the baseline failed, 0/8 passed |
| 05:18:34 | decide | Verified recommendation waiting for human approval |

## What Nemotron diagnosed (verbatim findings)

1. "Classification tasks use far fewer output tokens than the current 2048 token cap, indicating over-provisioning of model size and token budget." Evidence: mean completion 95.5, max 144, mean reasoning 92.2 tokens, and 4/4 passed on the large tier.
2. "Extraction tasks have one failure despite low token usage, suggesting the current large tier may be unnecessary for most cases and a retry mechanism could recover the failed case." Evidence: mean completion 287.5, max 368, and 3/4 passed on large.

Note that the analyst chose the **medium** tier, not the smallest one. It also set the token caps above the observed maxima (256 > 144, 512 > 368).

## Baseline vs verified candidate (same 8 tasks, temperature 0, one run each)

| Metric | Baseline (all Ultra) | Optimized (round 1) | Change |
| --- | --- | --- | --- |
| Tasks passed | 7/8 | 7/8 | same; no per-task regression |
| Inference cost | $0.005453 | $0.001980 | **−63.7%** |
| Total tokens | 2,389 | 2,112 | −11.6% |
| Completion tokens (incl. reasoning) | 1,532 | 1,118 | −27.0% |
| Model calls | 8 | 9 | +12.5% (one escalation) |
| Summed model latency | 9,677 ms | 12,906 ms | **+33.4%** |
| Wall time (tasks run concurrently) | 2,810 ms | 4,592 ms | +63.4% |
| Backend CPU time | 92 ms | 71 ms | — |
| Energy, central estimate | 0.790 Wh | 0.247 Wh | −68.7% (estimate) |
| GPU utilisation and memory | not observable | not observable | — |

**Tradeoff, stated plainly:** cost and estimated energy fell sharply, but this run was slower. Super was not faster per call than Ultra here, and `ext-04` escalated Super → Ultra (3.1 s). Latency on a shared serverless endpoint varies from run to run, and n=8 single runs cannot separate that noise from a real effect.

**The one failing task** (`ext-04`) fails in both configurations. The validator expects `name: "Priya Raman"`, and both models returned `"Dr. Priya Raman"`. The check is strict by design; we report it rather than loosening it after the fact.

**One-time cost and break-even:** the analysis cost $0.00307 and the verification run $0.00198. At $0.00347 saved per run of this workload, that spend is repaid after about 1.5 runs (2 runs, rounded up).

## Per-task detail

| Task | Baseline | Optimized | Optimized path | Request IDs (examples) |
| --- | --- | --- | --- | --- |
| cls-01 | pass | pass | Super | baseline `chatcmpl-84332844e50719b8`, optimized `chatcmpl-988fa837f154a2c5` |
| cls-02 | pass | pass | Super | in bundle |
| cls-03 | pass | pass | Super | in bundle |
| cls-04 | pass | pass | Super | in bundle |
| ext-01 | pass | pass | Super | in bundle |
| ext-02 | pass | pass | Super | in bundle |
| ext-03 | pass | pass | Super | in bundle |
| ext-04 | fail | fail | Super → Ultra (escalated) | baseline `chatcmpl-852910bd32628e67`, optimized `chatcmpl-bdb3bcc8f54aaeed` then `chatcmpl-a7ff8e5104c2c76e` |

## Limits of this evidence

- One workload, 8 tasks, one run per configuration. That shows the loop working on real inference and a real saving; it is not a statistically powered estimate of savings in general.
- The optimizer was verified on the same recurring workload it tuned. That is the intended use, and the result does not transfer automatically to other workloads.
- Cost uses the per-token prices configured in `.env`, multiplied by provider-reported tokens; check them against Nebius's current price list. Energy is a FLOPs-based estimate, not a power reading.
