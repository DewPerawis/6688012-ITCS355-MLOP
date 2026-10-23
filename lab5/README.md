# ITCS355 Lab 5 — Azure recovery milestone

Student: **6688012**. Primary provider: Azure, continuing Labs 2–4.
**The service works; the full Lab 5 submission is incomplete.**

## Verified result

On 23 October 2026 the student completed training, evaluation and registration of
`itcs355-6688012:3`. Validation PR-AUC was **0.40244651283160715**, test PR-AUC
**0.48110817994638944**. The real degraded candidate was blocked by the gate.
Managed deployment continuation `lab5-20261023-070538-deploy-repair-v2` completed;
the endpoint answered model version 3 with probability `0.005104794545095873` for
the recorded smoke request. This is one smoke request, not a capacity/load measurement.

The original six-step pipeline parent remains Failed. Recovery through a separate
managed deployment does not satisfy the handout's single-trigger requirement by itself.

- [Measured results and lineage](reports/managed-result.md)
- [Requirement-by-requirement status](reports/requirements-status.md)
- [Canonical execution state](reports/managed-execution.json)
- [Pre-run estimate](reports/lab5-estimate.md)
- [Cost report: final reconciliation pending](reports/lab5-cost.md)

## Architecture and operational guard

`src/` contains neutral data contracts, grouped splits, training and metric decisions.
`cloudlayer/` contains Azure orchestration, identities and deployment. Configuration
identifiers are inherited from the ignored Lab 2–5 cloud.env files; credentials are not
copied into the source bundle. Use WSL and the existing `itcs355-lab3` Python environment.

The six steps are ingest → validate → train → evaluate → register → deploy_staging.
Registration requires validation PR-AUC >= 0.4 and improvement >= 0.002 over incumbent
v1 (0.40004728306048276). Seed is 20260101. The test split does not select the candidate.
The single-seed gate is an operational guard, not statistical proof of a stable gain.
Model export uses the explicit cloudpickle format already used in Lab 2; load only our
own trusted model/checkpoint artifacts. Training and serving images are pinned by digest.

Training, serving and CI use separate managed identities. Serving startup needed
Storage Blob Data Reader at workspace storage-account scope and AcrPull at the registry.
The initial container-only Reader scope was insufficient. The recorded role correction
is not a deliberate permission-removal experiment; that assessed exercise remains pending.

## Current next steps

The student completed runtime cleanup at 17:19 Thailand time on 23 October 2026:
endpoint itcs355-6688012-lab5 and compute lab5train/lab5release were removed and rechecked
absent, no tagged schedules were found, and model v3 was retained. See cleanup-runtime.json.
Shared Storage/ACR remain; runtime deletion is not proof that every charge has stopped.

Use **notebooks/Lab5_Final_Batch.ipynb** for one continuous batch of offline tests,
provider audit, fresh read-only resource checks, fresh posted billing and a single
final-batch.md report/commit checklist. No old notebook reruns, new compute, cloud
mutations or Git changes are performed. Long billing throttles are reported while
other checks continue. The same notebook can be rerun after the 24-hour billing cutoff;
it does not wait for a day or introduce another numbered part.

The batch consolidates reporting; it does not simulate outstanding assessed work.
A single successful full pipeline execution, permission withdrawal, actual schedule,
second-provider demonstration and LLM/token evidence still need real execution.
Identity boundaries and the retraining comparison are in reports/operations-decisions.md.
See reports/requirements-status.md for exact remaining criteria. Portal screenshots
must still be checked manually. Do not describe the whole lab as completed yet.

## Offline checks

From `lab5/` in WSL/kernel itcs355-lab3:

```bash
python -m unittest discover -s tests -q
```

SDK 1.35.0 parsed the deployment-only definition and the bundle's local model reference.
The 21 offline checks verify gates, ownership, source/lineage boundaries, role scopes,
billing backoff and continuation isolation. They do not prove live cloud access or costs.
Provider-string audit of src returned zero matches in this review.

## Evidence and private files

Reports and saved notebook outputs retain successful runs and failures. The original
failed parent is not relabeled. Raw diagnostic bundles, credentials, local caches,
source snapshots and private planning instructions remain ignored. Shared resources
from previous labs must not be deleted by the Lab 5 runtime cleanup.

Handout: `lab1/course/labs/lab-05-cloud-mlops-and-cost.md` at student repository root.
