# ITCS355 Lab 2 — Experiment Tracking and Model Registry

Student ID: **6688012** · Provider: **Azure** · Region: **Central India**

This lab continues the reproducible machine-failure classifier from Lab 1. It moves the
digest-pinned training container to Azure Machine Learning low-priority compute, runs a
budgeted MLflow study, registers the chosen model with reconstructable lineage, promotes
it to Staging, and reloads the exact registry version to score held-out rows.

## Evidence status

The source, deterministic local tests, cost lookup, and managed-job workflow are prepared.
Cloud run IDs, metrics, registry version, interruption evidence, and actual Azure cost are
recorded only after those operations complete; this README intentionally does not invent
them in advance. Generated evidence belongs in `reports/lab2-*.json` and
`reports/lab2-comparison.md`.

## Reproduce the workflow

```bash
make setup
make data test portability-audit
make azureml-bootstrap
make image-push

# Use the digest returned by image-push, never a mutable tag.
make train-remote \
  IMAGE_URI='<registry>/itcs355@sha256:<digest>' \
  STUDY_ID='lab2-<commit>'

make compare
make register
make reload-check VERSION=<registered-version>
```

The first evidence run is submitted with `scripts/run_remote.py --interrupt-after 4`.
It writes its checkpoint to a persistent Azure ML datastore path and exits deliberately.
Submitting the same `STUDY_ID` again without that flag must print that the first four
trials were skipped and finish the study. This is a controlled test of the same resume
path needed after low-priority VM eviction; it is labelled as simulated rather than
misrepresented as an actual Azure eviction.

## Study design

The primary grid has exactly 12 distinct configurations:

- `n_estimators`: 80, 160, 240
- `max_depth`: 4, 8
- `min_samples_leaf`: 2, 8

All three parameters change model behaviour or capacity. The 12-configuration comparison
uses one fixed seed so configuration effects are not mixed with split effects. A candidate
is chosen by a predeclared rule: among runs within 0.005 absolute validation PR-AUC of the
best, choose the one with the lowest measured training cost. Five additional split/training
seeds then estimate mean, population standard deviation and spread for that configuration.
Held-out test metrics are logged for audit but never used for selection.

PR-AUC is the primary metric because only about 11.7% of rows are positive. It is not
described as accuracy. ROC AUC remains logged so later readers can compare with Lab 1.

## Budget and price evidence

The exact Linux `DS2 v2 Low Priority` meter for `Standard_DS2_v2` in Central India was
queried from the official Azure Retail Prices API on 2026-09-19: **1.1083 THB/hour**
(approximately 1.11 THB/hour). The on-demand Linux meter returned 5.558 THB/hour and the
Spot meter returned 1.1316 THB/hour. `src/costs.py` uses the exact low-priority value
returned by the API instead of an assumed discount factor.

Each run logs fit/evaluation wall time, instance and estimated THB. A conservative
10-minute projected duration is checked before starting each trial, and the study stops
before the next run could cross the 150 THB lab limit. Per-trial estimates exclude cluster
provisioning, storage and control-plane overhead; the final report must therefore compare
them with settled Azure Cost Management data rather than claiming they are the invoice.

The cluster is limited to one node, has `min_instances=0`, and scales down after 120 seconds.

## Lineage and model promotion

`cloudlayer.azure.AzureAdapter.register_model()` refuses to register unless the chosen
MLflow run provides all eight required model-version tags:

```text
git_commit       data_version       mlflow_run_id       training_job_id
image_digest     seed               metric_val          metric_test
```

Registration uses `runs:/<run-id>/model`, preserving run-to-model lineage. Promotion is a
separate transition to the case-sensitive MLflow stage `Staging`. The reload check loads
`models:/<name>/<version>`—not a local pickle and not `latest`—then predicts five held-out
rows with the preprocessing contract packaged in the MLflow model.

In a real organisation, a release owner or model-risk approver should own promotion, not
the identity that trained the candidate. Required evidence should include exact code,
data and image lineage; validation and held-out metrics; seed variance; cost; data/security
checks; and a successful registry reload test. This separation prevents training automation
from silently approving its own output.

## Identity boundary

The submitter identity creates the job. The running job uses Azure ML user-identity
passthrough to read the private Blob input and write the persistent checkpoint/output.
No storage key, SAS URL, Azure token, `cloud.env`, raw CSV, MLflow database or DVC cache is
committed or copied into the image.

## Lab 1 lineage carried forward

- DVC version: `1c886b512c8a5c9bf723da1cd119fc80.dir`
- Data fingerprint: `422cccb9136e8140`
- Group split: deterministic by `machine_id`
- Final Lab 1 image digest: `sha256:f8eaad5b655af10fc43e6155afa844dd397f850fe665b0a1aa94b9cd088b259a`

The Lab 2 image receives a new digest because it adds the Azure ML/MLflow integration and
the study code. The Lab 1 digest is provenance, not the image claimed for Lab 2 execution.

## Submission checklist

- [ ] Azure ML workspace/datastore and low-priority scale-to-zero compute verified
- [ ] Digest-pinned Lab 2 image pushed
- [ ] First managed job interrupted after a persistent checkpoint
- [ ] Resume job completed 12 configuration trials and 5 seed trials
- [ ] `reports/lab2-comparison.md` contains measured results and <=200-word decision
- [ ] Selected model registered with all eight lineage fields
- [ ] Version promoted to Staging and reloaded by exact version
- [ ] Settled Azure cost checked; total remains below 150 THB
- [ ] Nonessential compute/jobs removed only after evidence is preserved
