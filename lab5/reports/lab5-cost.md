# Lab 5 — Cost report (execution observed; reconciliation pending)

## 1. Estimate before running

See [lab5-estimate.md](lab5-estimate.md) for price evidence and explicit assumptions.
Pre-run commit SHA: `83c400d616b3323c292d9c028fd80cfd9e1200ba`, recorded by the student's
Part 3 execution on 23 October 2026 at 13:31 Thailand time. Managed execution and deployment continuation are now recorded in `managed-execution.json`;
see `managed-result.md` for the successful stages and the failed original parent.

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
final measured durations, usage and allocated actual charges pending. The successful model
is v3; the serving continuation completed and passed its smoke test. Do not price only
the final successful attempt: failed training/deployment attempts also consumed resources. Avoid shared-cost double counting.

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

## Cleanup and consolidated final review

The user removed the named Lab 5 endpoint and two compute clusters and rechecked their
absence on 23 October 2026 at 17:19 Thailand time. Model v3 and shared Storage/ACR were
retained. See cleanup-runtime.json. This does not establish zero future or shared charges.
Lab5_Final_Batch.ipynb queries fresh posted billing into reports/final-batch.json and
final-batch.md without reusing the pre-execution billing cache. Run the same notebook
at least 24 hours after teardown for the later observation. Final cost/FX allocation,
20% estimate agreement and the full-term <800 THB condition remain unverified.
