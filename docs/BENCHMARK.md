# EcoBench v1 held-out benchmark (real Nebius runs, 2026-10-30)

Everything here is computed from the committed bundles. Nothing was re-run, edited or filtered.

| Run | Split | Conditions | When (UTC) | Calls | Bundle |
| --- | --- | --- | --- | --- | --- |
| `c143a70690b64c44` | calibration (14 tasks) | fixed:small, fixed:medium, fixed:large | 2026-10-30 09:00 | 42 | [json](../benchmarks/results/run-c143a70690b64c44-nebius.json) |
| `1c62f1ef2642451f` | **held-out test (35 tasks)** | fixed:large, adaptive, adaptive_warm | 2026-10-30 09:02 | 115 | [json](../benchmarks/results/run-1c62f1ef2642451f-nebius.json) |
| `895becc994d74ff5` | held-out test (35 tasks), replicate | fixed:large, adaptive, adaptive_warm* | 2026-10-30 05:59 | 117 | [json](../benchmarks/results/run-895becc994d74ff5-nebius.json) |

Setup: Nemotron Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`), Super (`nvidia/nemotron-3-super-120b-a12b`) and Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`) on Nebius Token Factory. Temperature 0, max 2,048 output tokens, one repeat. Each task has a deterministic check. All conditions run the same task back to back. The baseline is `fixed:large`: always Ultra, no escalation.

\* Run `895becc…` happened before any calibration run existed, so its `adaptive_warm` had no calibration evidence (`observed_n = 0` in every routing decision). It routed exactly like `adaptive` (35/35 identical start tiers). It is reported as a second cold-start replicate, not as a warm-start result.

## Primary result: run `1c62f1ef2642451f` (after calibration)

| Condition | Passed | Pass rate (95% Wilson CI) | Total cost | Cost / task | Cost / success | Median latency | p95 latency | Tokens / task | Calls | Escalation rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed:large (baseline) | 33/35 | 94.3% [81.4, 98.4] | $0.034298 | $0.000980 | $0.001039 | 1,124 ms | 2,923 ms | 394.7 | 35 | 0% |
| adaptive (prior only) | 34/35 | 97.1% [85.5, 99.5] | $0.007423 | $0.000212 | $0.000218 | 1,886 ms | 6,860 ms | 409.3 | 39 | 5.7% |
| adaptive_warm (calibration evidence) | 34/35 | 97.1% [85.5, 99.5] | $0.006585 | $0.000188 | $0.000194 | 1,570 ms | 5,713 ms | 427.4 | 41 | 8.6% |

**Paired comparison with the baseline (35 tasks, paired bootstrap 95% CIs):**

| | Pass-rate difference | Cost change | Tokens change | Mean latency change | Per-task outcomes |
| --- | --- | --- | --- | --- | --- |
| adaptive | +2.9 pts [0.0, +8.6] | **−78.4%** [−87.8, −65.7] | +3.7% [−16.2, +25.9] | **+72.0%** [+30.8, +120.8] | 33 both pass, 1 both fail (ext-04), 1 gained (ext-06), **0 lost** |
| adaptive_warm | +2.9 pts [0.0, +8.6] | **−80.8%** [−93.0, −66.0] | +8.3% [−17.0, +38.1] | **+62.5%** [+19.5, +118.4] | 33 both pass, 1 both fail (ext-04), 1 gained (ext-06), **0 lost** |

**Model usage:**

| Condition | Started on | Finished on |
| --- | --- | --- |
| fixed:large | Ultra 35 | Ultra 35 |
| adaptive | Nano 24, Super 11 | Nano 22, Super 11, Ultra 2 |
| adaptive_warm | Nano 35 | Nano 32, Ultra 3 |

Calibration showed Nano passing 12/14 calibration tasks (one quality miss, one provider overload error), so the warm router starts everything on Nano and relies on the validators to escalate. It escalated 3 tasks (sum-03, sum-04, ext-04); two of them passed on Ultra.

## What we can and cannot claim

- **Cost:** both adaptive conditions cost 78–81% less than always using Ultra. The 95% intervals exclude zero in both runs.
- **Quality:** on the held-out tasks, no task that passed on Ultra failed under adaptive routing, in either run (0 losses in 4 paired comparisons × 35 tasks). The pass-rate difference interval includes zero, so we do **not** claim higher quality. The one "gain" (ext-06) comes from a strict check: Ultra answered `"TrailLite 2 tent"` where the label is `"TrailLite 2"`.
- **Latency is worse.** Adaptive routing was 62–72% slower on mean latency, and p95 roughly doubled. Two causes are visible in the data: Nano was slow per call on this endpoint (calibration median 6.1 s for Nano vs 1.0 s for Ultra; it also returned one HTTP 529 "worker overloaded"), and escalations add calls in sequence. This is a real tradeoff for latency-sensitive traffic.
- **Tokens did not fall.** Smaller models used about as many tokens, including reasoning tokens. The savings come from price per token, not from fewer tokens.
- **Warm vs cold:** the calibration evidence moved 11 start decisions from Super to Nano and saved a further 2.4 points of cost. The difference between warm and cold is within run-to-run noise (see the replicate).

## Replicate: run `895becc994d74ff5` (no calibration evidence)

| Condition | Passed | Cost | Cost / task | Median | p95 | Tokens / task | Calls | Escalations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed:large | 32/35 | $0.032441 | $0.000927 | 1,125 ms | 1,751 ms | 377.1 | 35 | 0% |
| adaptive | 33/35 | $0.010138 | $0.000290 | 1,899 ms | 6,001 ms | 465.6 | 41 | 8.6% |
| adaptive_warm (no evidence, = cold) | 33/35 | $0.008779 | $0.000251 | 2,074 ms | 6,360 ms | 466.9 | 41 | 8.6% |

Versus the baseline: adaptive cost −68.7% [−83.6, −52.1], latency +113%; the second cold run cost −72.9% [−83.7, −59.5]. Per-task: 0 losses for both. Tokens rose 23–24% in this run (interval excludes zero).

**Non-determinism at temperature 0.** The two cold-start conditions in this run made identical routing decisions but did not produce identical outcomes: `ext-06` passed in one and failed in the other, and `sum-04` the reverse. Ultra also failed `sum-04` in this run ("Nov 20" instead of "November 20") and passed it in the primary run. Single-run differences of one task are noise, which is why we report paired per-task outcomes and intervals rather than headline pass rates.

## Calibration run `c143a70690b64c44` (routing evidence only, not a reported result)

| Condition | Passed | Cost | Median latency | Lost vs Ultra |
| --- | --- | --- | --- | --- |
| fixed:small (Nano) | 12/14 | $0.000652 (−94%) | 6,064 ms | ext-02 (quality), json-01 (provider error: HTTP 529 "worker overloaded", counted as a failure) |
| fixed:medium (Super) | 14/14 | $0.002682 (−76%) | 2,004 ms | none |
| fixed:large (Ultra) | 14/14 | $0.011304 | 1,020 ms | — |

## Every quality failure

| Task | Where it failed | Validator message |
| --- | --- | --- |
| ext-04 | every condition, every tier, both runs | `name: expected 'Priya Raman', got 'Dr. Priya Raman'` |
| ext-06 | Ultra (both runs); Nano→Super→Ultra chain in one replicate condition | `product: expected 'TrailLite 2', got 'TrailLite 2 tent'` |
| sum-04 | Ultra and one cold condition in the replicate | `contains_all: missing 'November 20'` (answer said "Nov 20") |
| sum-03 | Nano and Super (rescued by escalation to Ultra) | `contains_all: missing 'load balancer'` |

These checks are strict by design, and we did not loosen them after seeing the results.

## Independent verification

`python scripts/verify_benchmark.py` re-checks every committed bundle offline, without an API key. On these runs it reports PASS for each of these checks:

- Calibration (14) and held-out (35) case IDs are disjoint. Each test run used only held-out cases.
- Stored cost equals the provider-reported prompt and completion tokens × the configured prices, for every condition. So the −78.4% and −80.8% follow directly from raw token counts.
- Cold `adaptive` used no observed evidence. In the primary run, `adaptive_warm` evidence counts per (category, tier) never exceed the calibration-run attempts, so no held-out task informed its own routing.
- Every successful call carries a provider request ID (115 of 115 in the primary run).
- Provider errors are listed apart from quality failures. There was one: Nano, json-01, HTTP 529 during calibration.

## Cost of running this benchmark

All three runs together cost about $0.11 in provider-reported tokens at the configured prices.
