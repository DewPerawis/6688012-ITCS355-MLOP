# Lab 3 — Load, canary, rollback, and cost report

## Predeclared target

Committed before endpoint measurement: warm client-observed end-to-end p95 below **250 ms** at **10 VUs**, HTTP
error rate below **1%**, measured for **60 seconds** after a **15-second warm-up**.

The target was not changed after measurement. The 10-VU run missed the latency target while meeting the error target.

## Endpoint and lineage

- Production model: `itcs355-6688012` version `1` (from Lab 2)
- Serving image: `itcs355-serve@sha256:4e7f94595568e706e09a31a1a2a51247452fdc4c2a70d877b09fb3248b82291d`
- Endpoint/deployment: `itcs355-6688012-lab3` / `blue`
- Region/instance: Central India / `Standard_DS2_v2`, one instance
- Retail price evidence: **5.558 THB/hour**, Azure Retail Prices lookup on 2026-09-27; stored in `azure-vm-prices.json`

## Concurrency and breaking point

All rows use a 60-second measured window after a 15-second warm-up.

| VUs | successes | predictions/s | p50 ms | p95 ms | p99 ms | error rate | target met |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 531 | 8.85 | 111.50 | 116.07 | 123.95 | 0.00% | yes |
| 5 | 2,123 | 35.38 | 142.04 | 169.64 | 180.46 | 0.00% | yes |
| 7 | 2,401 | 40.02 | 182.11 | 210.76 | 228.40 | 0.00% | yes |
| 8 | 2,566 | 42.77 | 195.49 | 225.02 | 280.98 | 0.00% | yes |
| 9 | 2,667 | 44.45 | 213.10 | 244.27 | 301.26 | 0.00% | yes |
| 10 | 2,714 | 45.23 | 234.05 | 266.31 | 329.40 | 0.00% | **no** |
| 50 | 2,066 | 34.43 | 111.02 | 1,366.49 | 1,742.26 | 78.07% | **no** |

The declared target is sustainable through **9 VUs**; the first latency breaking point is **10 VUs**. At 50 VUs,
7,349 responses were HTTP 429, so queue/concurrency saturation rather than model errors dominated. Cold-start request
latency was not separately measured; all reported load windows are warm and exclude endpoint provisioning.

## Batch size, payload size, and instance size

| Experiment | Baseline | Variant | Result | Interpretation |
|---|---|---|---|---|
| single vs batch 100, 1 VU | single: 8.85 predictions/s, p95 116.07 ms | batch 100: 846.67 predictions/s, p95 120.83 ms | about 95.7× prediction throughput for 4.1% higher p95 | Batch amortises request/network overhead when callers can accumulate records. |
| payload size, 1 VU | no padding: 8.85/s, p95 116.07 ms | 10 KB: 8.67/s, 118.57 ms; 100 KB: 8.08/s, 127.77 ms | larger payload reduced throughput and increased latency | Avoid unused request context; schema should carry only inference features. |
| instance size, 10 VUs | DS2 v2: 45.23/s, p95 266.31 ms, 5.558 THB/h | DS3 v2: 46.17/s, p95 261.25 ms, 11.0831 THB/h | +2.1% throughput and -1.9% p95 for +99.4% hourly cost; still misses target | Keep DS2 v2 and cap the declared SLO load at 9 VUs; scaling up one size is poor value. |

The exact minimum batch break-even size was not measured because only sizes 1 and 100 were tested. At the measured
size of 100, batching is decisively cheaper per prediction; workloads requiring immediate single-row responses should
remain online, while delay-tolerant groups should use batch requests.

## Canary and rollback

- Canary: model version `2`, deliberately worse Lab 2 run `49fd25d0-0b36-4958-ae0f-905190a2bb25`; registered validation PR-AUC 0.389062 versus production reference 0.400047283
- Traffic changed from 100/0 to 90/10 at `2026-09-28T00:27:56.684331+00:00`
- Detection rule: live validation PR-AUC absolute drop at least 0.005 after at least 50 samples for each version
- Detected at `2026-09-28T00:56:22.727885+00:00`, after 1,708.674 seconds and 540 requests
- Live metrics: v1 = 0.39828958, v2 = 0.26984127; observed absolute drop = 0.12844831
- Samples: v1 = 488, v2 = 52
- Rolled back to blue/green 100/0 at `2026-09-28T00:57:03.424203+00:00`
- Deleted `green` at `2026-09-28T01:02:10.766741+00:00`

Analysis: (1) PR-AUC matches the imbalanced binary-classification objective. (2) Detection took about 28.5 minutes
because only 10% of traffic reached the canary and each version required 50 labelled samples. (3) A staged replay or a
higher temporary canary share would detect degradation faster. (4) A 50/50 split would collect canary evidence roughly
five times faster but expose more users to the worse model. (5) The 90/10 policy trades slower detection for a smaller
blast radius, and the measured rollback restored production before the canary deployment was deleted.

## Cost per 1,000 predictions

Formula: `hourly THB / (measured predictions/s × 3600 × utilisation) × 1000`.

- Sustainable online rate: 44.45 successful predictions/s at 9 VUs
- Assumption: the paid instance is available for the whole hour but useful prediction traffic occupies 25% of its measured capacity
- Online cost: **0.1389 THB per 1,000 predictions** at 25% utilisation
- Batch-100 rate: 846.67 predictions/s; estimated **0.0073 THB per 1,000 predictions** at the same utilisation
- These are compute-only estimates based on the captured retail VM price; Azure ML management, storage, networking, tax, and idle deployment time may add cost

## Teardown

- Canary deployment `green`: deleted at `2026-09-28T01:02:10.766741+00:00`
- Production endpoint `itcs355-6688012-lab3`: deletion completed at `2026-09-28T01:40:12.418443+00:00`
- Azure SDK absence verification completed at `2026-09-28T01:40:15.441241+00:00`
- Azure Portal visual confirmation: perform once before submission; it is not claimed by this automated check
- Settled Cost Management check: review later because Azure billing data can lag
