# Lab 5 — Cost report (execution and reconciliation pending)

## 1. Estimate before running

See [lab5-estimate.md](lab5-estimate.md) for price evidence and explicit assumptions.
Pre-run commit SHA: `83c400d616b3323c292d9c028fd80cfd9e1200ba`, recorded by the student's
Part 3 execution on 23 October 2026 at 13:31 Thailand time. No Task 1 execution is recorded yet.

## 2. Actual billing

The student's Part 3 query succeeded after bounded HTTP 429 backoff. The course resource
group had **USD 7.896070275116232** posted pretax charges for the observation window
1 September–23 October 2026. Most was shared ACR (USD 6.6747595278), followed by ML
workspace usage (USD 1.220457387316232); see `billing-review.json` for retained rows.
The Lab 5 tag-filtered query returned no posted rows at this pre-execution observation.
This is not a Lab 5 actual total and is not evidence of zero consumption. Full-term THB
reconciliation, exchange-rate basis, other scopes and late charges remain unverified.

See `planning.json` for the pre-run RG observation and Lab 5 tag-filtered observation.
These are posted observations, not final Lab 5 consumption. Empty rows are not proof of zero cost.
Final tagged billing, +24h teardown check, FX source and <800 THB full-term reconciliation: pending.

## 3. Estimate versus actual gap

Pending actual charges. Report absolute and percentage differences, scope and exclusions.
Do not treat billing lag or a credit-funded subscription as free usage.

## 4. Component breakdown

Training, storage, serving, pipeline and monitoring: estimate in the linked pre-run report;
measured durations, usage and allocated actual charges pending. Avoid shared-cost double counting.

## 5. Cost per 1,000 predictions

Pending measured sustainable capacity and serving hourly cost.
Formula: hourly cost / (measured predictions per hour at full utilisation × utilisation) × 1,000.

| Utilisation assumption | THB / 1,000 predictions |
|---|---|
| 5% | pending measurements |
| 25% | pending measurements |
| 80% | pending measurements |

## 6. Applied optimisation

Pending measured before/after under the same workload. No optimisation result claimed yet.

## 7. LLM token bill and budget defence

Pending provider/model access, real usage fields and current rates; no word-count token estimates.
Record measured baseline/capped runs and eval gate, cache economics versus observed hits,
and a short nontechnical budget defence after obtaining the measurements.
