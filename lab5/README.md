# ITCS355 Lab 5 — Operating LLM Systems and Defending the Bill

Student: **6688012**. Primary provider: **Azure**, continuing from Labs 2–4.

## Current implementation status

The student's 16:24 audit confirms the missing permission: the correct serving identity
has AcrPull on workspace ACR but no unconditional Blob data reader role at workspace
storage-account scope. Endpoint/model/image binding is verified: model
`itcs355-6688012:3`, validation PR-AUC `0.40244651283160715`, test PR-AUC
`0.48110817994638944`, training/MLflow run `f115d4dd-f69c-4195-8c1c-f4a87f9bbf3d`,
source commit `4f3a8957ded20901989fa48bbe58be29c33f6578`. Both compute clusters had
zero nodes at that audit; the failed staging deployment still exists.

**Next step: [`notebooks/05f_repair_deployment_only.ipynb`](notebooks/05f_repair_deployment_only.ipynb).**
The user-run cell rechecks the audited model, identity, roles, compute and immutable
source bundle, parses a deployment-only pipeline, adds only the missing Storage Blob
Data Reader grant to the serving identity on the existing workspace storage account,
allows 90 seconds for propagation, and submits/observes one deterministic
`lab5-20261023-070538-deploy-repair` job. It uses the existing registration job's output
under the CI identity. There is no training, registration, Git mutation or resource setup.
Release compute and staging can incur charges. A replay observes the same job name.
It verifies exact model binding, successful deployment and a scoring response, preserves
registry versions, and retrieves failure diagnostics automatically. Staging stays open
for evidence capture/cleanup. The original parent remains Failed; a successful deployment
continuation is recorded separately rather than relabeling that parent as successful.

Offline preparation was checked in the student's existing WSL Python 3.11.16 environment:
SDK 1.35.0 parsed the one-node pipeline, verified the actual saved candidate/bundle, and
accepted the hyphenated container log names. All 20 offline tests passed there. No
Azure calls, role grants, managed execution or Git commits were performed by the
assistant during those checks. These checks do not prove live deployment success.

The previous audit used container names from the API reference that SDK 1.35.0 rejects.
It now uses `storage-initializer` / `inference-server`, verified with that SDK's validator.
The future role preview source plans Blob Reader at workspace storage-account scope;
this source correction alone has not changed Azure access or historical frozen bundles.

The full lab still requires a successful normal pipeline, identity-withdrawal evidence,
schedule/retraining discussion, second-provider demonstration, Part B LLM evidence,
cost reconciliation and teardown. Prepared code or offline checks do not satisfy
those managed/evaluated requirements by themselves.

Part 4 passed on the student's rerun at 13:51 Thailand time, 23 October 2026. The real
data contract and grouped split (3600/1200/1200 rows) passed; deliberate contract/gate
probes were blocked; both pipeline definitions parsed with SDK 1.35.0. Input metadata
and both pinned images were readable. These are preparation results, not managed runs.

Part 5: [`notebooks/05_managed_pipeline.ipynb`](notebooks/05_managed_pipeline.ipynb).
This explicit user-run part commits only allowlisted implementation source locally,
creates/verifies two Lab 5 identities, the eight previewed scoped assignments, and two
min=0/max=1 compute clusters. It runs a degraded candidate first and checks failure at
evaluate without registration or endpoint creation, then runs the normal six-step path.
The serving endpoint remains running after success; evidence capture and cleanup follow.
Nothing has been executed by the assistant and no managed-run result is claimed yet.

Execution records intended job names before submission and resumes observing existing
jobs on rerun. Existing staged work, foreign-resource tags, unexpected identity/compute
shapes and scope changes stop execution. Model/endpoint release uses the CI identity on
separate compute. Before deployment, release waits for training nodes to scale to zero
and inspects the registered model's downloaded layout for the serving mount path.

Budget screening uses an explicit conservative **planning** assumption of 40 THB/USD
and a 200 THB reserve for unposted/other-scope costs, plus the committed 44.8282 THB Lab 5
envelope. At the observed USD 7.896070275116232 this totals 560.6710 THB. These are not
measured FX, actual reserves spent, proof of full-term coverage, or an enforced billing
cap. The notebook says to stop if known other costs exceed that reserve. Discounted
compute remains unmet; dedicated execution does not silently satisfy that requirement.

The first Part 4 attempt passed its data/gate rehearsal and read-only cloud checks,
then failed in local `load_job` parsing: SDK 1.35.0 rejects `identity.resource_id` in
job YAML. This was a compiler error, not an account/permission failure. Training nodes
now use `identity: {type: managed}` and require a compute with only the training UAI
attached. Release nodes still select the CI identity explicitly by `client_id`.
The Python identity constructor and job YAML schema have different accepted fields.
The corrected document passed full local SDK parsing on the student's rerun. The failed
generated YAML and bundle were preserved locally for diagnosis.

Part 3 completed on 23 October 2026: the student committed the pre-run estimate as
`83c400d616b3323c292d9c028fd80cfd9e1200ba`. Billing succeeded after backoff: the course RG
had USD 7.896070275116232 posted pretax charges in the observed window; the Lab 5 tag query
had no rows. No full-term THB total or zero Lab 5 bill is claimed.

Part 4: [`notebooks/04_pipeline_preview.ipynb`](notebooks/04_pipeline_preview.ipynb).
This user-executed part rehearses the real Lab 2 data contract and synthetic gate boundaries,
reads cloud input metadata and verifies both historical image digests in ACR. It emits and
locally parses the six-node Azure pipeline plus a variant training a genuinely degraded
prior-only classifier. It previews separate training/release compute, serving identity,
and exact role scopes. No resources/permissions/jobs are created by this part.

The normal candidate uses the fixed-seed Lab 2 split and a 240-tree, depth-8, min-leaf-8
random forest. The validation gate requires PR-AUC >=0.40 and improvement >=0.002 over
the explicitly bound version-1 incumbent. Held-out test scores do not select candidates.
The margin is an operational demonstration rule, not a statistically established gain.
Release nodes require the gate output and recheck metrics/lineage before registering;
the managed fail/no-registration evidence is still pending execution.

Only allowlisted runtime source enters a regenerable `_bundles/` directory; env files,
other Labs, raw data and credentials are excluded. Before any managed submission, source
must be committed and the preview regenerated against that revision. Preview base-commit
metadata alone is not evidence that the uncommitted implementation is versioned.

The student ran Part 2 on 23 October 2026 at 13:21 Thailand time. Quota parsing now
succeeded. Total dedicated-core quota was 20, one DSv2-family entry was 6, and total
low-priority-core quota was 0. Duplicate family entries with limit -1 are retained as
observations, not interpreted as unlimited capacity. No discounted-compute requirement
is marked complete. Dedicated compute is only a proposed fallback and its availability
and endpoint headroom remain to be validated before execution.

Both Cost Management queries returned HTTP 429. Actual costs and full-term budget
headroom remain pending. Billing requests now honor the longest applicable throttle
header, retry at most three times, and defer server cooldowns over 60 seconds. Successful
standalone billing observations under 24 hours old are reused on rerun.

Part 3: [`notebooks/03_freeze_estimate.ipynb`](notebooks/03_freeze_estimate.ipynb).
This user-executed notebook retries billing and commits only `reports/lab5-estimate.md`
locally after checking its Part 2 SHA-256 and an empty Git staging area. It does not push
or start resources. A pending billing result does not authorize billable execution.
The estimate is 17.3568 THB for the Part A planning subtotal and 44.8282 THB including
explicit future-service reserves/contingency. Those reserves are not verified prices.
The recorded estimate-commit SHA must be checked again before submitting a managed job.

The student ran Part 1 on 23 October 2026 at 13:14 Thailand time. WSL, Docker,
workspace/model access and resource listing passed. The exact incumbent is version 1,
with validation PR-AUC `0.40004728306048276`. Compute, online endpoint and schedule lists
were empty at that observation. This does not mean the shared workspace/Storage/ACR
are absent or free. Six current DS2 v2 retail meters were returned.

Quota parsing raised `AttributeError`: SDK 1.35.0 copies the REST dictionary into a
`Usage` object, so its nested `name` may remain a dictionary. The parser now accepts
both dictionary and object forms, and rejects missing usage/limit values. Three focused
offline tests passed; the repaired live quota call is still pending student execution.

Part 2: [`notebooks/02_quota_estimate.ipynb`](notebooks/02_quota_estimate.ipynb)
in the same WSL environment. It reads only quota, managed identities and posted billing,
then prepares a reviewable estimate from Part 1's price evidence. There is no need to
rerun all of Part 1. Existing estimates/cost reports are preserved on rerun.
The billing observation window starts 1 September 2026; it is not asserted to be the
official semester start or sufficient evidence of full-term spending. Resource-group
and Lab-5-tag-filtered observations are kept separate. No FX or actual-cost total is invented.

The estimate's noncompute allowances and future LLM/second-provider reserves are proposals,
not measured charges or service quotes; review them before using those services. The
short demonstration runtime assumptions and unverified term-budget headroom must also
be reviewed before committing the estimate and starting Task 1.

The first user-executed notebook is ready:
[`notebooks/01_lab5_start.ipynb`](notebooks/01_lab5_start.ipynb).
It inspects the WSL environment, existing Azure ML workspace and exact incumbent model,
available compute, endpoints, schedules, quota, resource inventory and current VM retail meters.
It creates no cloud resources, installs no packages and performs no training or Git changes.

Run the single code cell using the previous Lab 4 WSL Python environment.
The equivalent terminal entry point, from `lab5/`, is:

```bash
python -u -m scripts.preflight
```

The report `reports/preflight.json` records the user's observation time, source hashes,
workspace/model metadata and the checks that could not be completed. Repeated runs preserve
the previous report under `reports/preflight-history/`. Optional inventory/price failures
remain explicit and must be resolved before using those inputs to deploy or estimate cost.
The printed summary omits subscription/tenant IDs and configuration secrets.

Configuration identifiers are read in order from Lab 2, Lab 3, Lab 4 and optional Lab 5
`cloud.env`; later nonempty values override earlier ones. Exported identifiers take precedence.
No environment file is executed, copied, printed or uploaded. SDK authentication uses the
existing Azure CLI login and the configured subscription.

## Remaining assessed work

This is readiness tooling, **not a completed Lab 5**. The managed pipeline, scoped-identity
experiment, retraining schedule, second-provider demonstration, LLM recordings/gates,
token optimisation, cost reconciliation and verified teardown remain to be implemented/run.
An estimate must be reviewed and committed before the first managed pipeline execution.
The user currently has Azure only; Task 4's second provider and Part B's LLM access remain
unresolved requirements. Neither is required to run this first readiness notebook.

VM retail meters are references, not the Azure Students invoice, and do not include every
ML/storage/logging/registry charge. THB retail prices are budget references. Billing remains
pending until queried and reconciled; no term-spend or cost-compliance result is claimed.

## Sources

- Course handout: `course/labs/lab-05-cloud-mlops-and-cost.md` in the teaching repository.
- [Azure MLClient](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.mlclient?view=azure-python).
- [Azure ML compute and quota inspection](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.operations.computeoperations?view=azure-python).
- [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).
- [Cost Management throttling](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/manage-automation).
