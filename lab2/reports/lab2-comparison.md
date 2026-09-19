# Lab 2 — Run comparison

Study `lab2-6e10bd9` · experiment `itcs355-lab2` · 12 configuration trials · 5 seed trials · estimated trial compute 0.016551 THB.

Selection metric: `val_pr_auc`. Held-out test PR-AUC is shown for audit only and was not used to select the candidate.

| run_id | val_pr_auc | test_pr_auc | cost_thb | duration_s | trees | depth | min_leaf | thb_per_point |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| e3544be6-5b47-4e82-8d4c-fde7d4bf59df | 0.402447 | 0.481108 | 0.001431 | 0.926765 | 240 | 8 | 8 | 0.000689 |
| dfba7e52-ea66-47df-8ecd-503c159ade1a | 0.401796 | 0.475376 | 0.001085 | 0.702903 | 160 | 8 | 8 | 0.000539 |
| lab2-20260919-151227--6e10bd9 | 0.400783 | 0.491008 | 0.000911 | 0.590121 | 80 | 4 | 2 | 0.000477 |
| 9b7ff1c3-1a06-4557-a16e-e753ded72079 | 0.400047 | 0.466108 | 0.000643 | 0.416557 | 80 | 8 | 8 | 0.000350 |
| 49fd25d0-0b36-4958-ae0f-905190a2bb25 | 0.389062 | 0.501030 | 0.001323 | 0.857110 | 240 | 4 | 2 | 0.001793 |
| c632f551-9e7e-465f-b8ec-11bcfef28f61 | 0.389051 | 0.490937 | 0.000670 | 0.433999 | 80 | 4 | 8 | 0.000909 |
| 4870a032-f1af-462d-9b82-176d2404afe4 | 0.388417 | 0.499028 | 0.001285 | 0.832401 | 240 | 4 | 8 | 0.001908 |
| lab2-20260919-152043--6e10bd9 | 0.387612 | 0.496591 | 0.001627 | 1.054028 | 160 | 4 | 2 | 0.002743 |
| 7c548778-227c-47b8-a8a7-e1eaae1db128 | 0.384522 | 0.494617 | 0.001020 | 0.660904 | 160 | 4 | 8 | 0.003590 |
| 3a4b8596-4549-4e0c-879e-a3962ea5680c | 0.384180 | 0.476594 | 0.001529 | 0.990579 | 240 | 8 | 2 | 0.006119 |
| ab85f8ef-9fce-42b0-9e6a-b295985cb173 | 0.381739 | 0.478874 | 0.001168 | 0.756398 | 160 | 8 | 2 | 0.198928 |
| 3bb4484b-d68b-42d2-88ec-d8a928493387 | 0.381680 | 0.471234 | 0.000689 | 0.446486 | 80 | 8 | 2 | — |

## Decision (200 words maximum)

I selected run `9b7ff1c3-1a06-4557-a16e-e753ded72079` with n_estimators=80, max_depth=8 and min_samples_leaf=8. It is 0.002399 below the highest single-run score, inside the declared 0.005 near-best band, and had the lowest measured training cost in that band. Across 5 seeds, validation PR-AUC averaged 0.461194 (population SD 0.045570, spread 0.117397), so I do not interpret the single-run lead as a stable accuracy gain. The measured compute estimate was 0.000643 THB for this fit and 0.000634 THB for one monthly retrain at the same size; Azure provisioning and storage are excluded and actual billing must be checked separately. This choice could be wrong if production class balance or machine behaviour differs from the synthetic held-out groups, changing both PR-AUC ranking and the useful complexity level.

## Cost and interruption evidence

- Verified DS2 v2 (Linux Consumption) in `centralindia` at 5.5580 THB/hour using the Azure Retail Prices API on 2026-09-19.
- Per-trial estimates use measured fit/evaluation wall time multiplied by that rate; they do not claim to equal the final Azure invoice.
- The persistent checkpoint and 2 job records for study `lab2-6e10bd9` are retained in `reports/lab2-jobs.json`; the first job intentionally stops after a saved trial and the second job resumes the same study path.

## Promotion ownership

In a real organisation, a release owner or model-risk approver—not the training-job identity—should promote to Staging. They should require reproducible code/data/image lineage, review of validation and held-out metrics, seed variance, cost, security and data-contract checks, and a successful registry reload test. Separation of duties prevents the person or automation that produced a candidate from silently approving it.
