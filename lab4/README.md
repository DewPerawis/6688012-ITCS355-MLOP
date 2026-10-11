# ITCS355 Lab 4 — CI/CD, Observability, and Drift

Student: **6688012**. Provider: **Azure**. Source: Lab 3 service and adapter, Lab 2
registry model `itcs355-6688012:1`, deterministic dataset seed `20260101`.
The authoritative handout is `course/labs/lab-04-cicd-monitoring-drift.md` in the teaching repository.

## Evidence status

This folder is prepared for execution. Local tests, a deliberately failing local contract
rehearsal, a real serving-container smoke test, and local drift calibration are checked.
The assistant's local checks are preparation evidence. **They do not complete the required
failing GitHub PR, staging deployment, scheduled cloud detector, real alert receipt,
injected-drift dashboard capture, or cloud teardown.** See `reports/lab4-status.md`.

## Reproduce the checks

Use Python 3.11. Install with the committed hash lock in an isolated environment:

```bash
python -m pip install --require-hashes -r requirements.txt
python -m scripts.prepare
make lint
make test
make local-drift
python -m scripts.contract_rehearsal
```

On the owner's existing WSL environment, `bash run_local_checks.sh` uses the Lab 3
environment and requires no new dependency installation. On a fresh clone, create an
environment and install the lock first. The data and CI fixture are regenerated locally.
The CI model is for tests only; deployment always uses the existing exact registry version.

## What the tests protect

| Contract | Production incident it catches | Named test |
|---|---|---|
| Exact columns and numeric features | Producer drops `temp_c`, renames a field, sends numeric strings, or adds an unexpected field | `test_training_schema_contract`, `test_schema_rejects_missing_and_unknown_features` |
| Plausible ranges and zero null/non-finite rate | Celsius/Fahrenheit or sensor-calibration error produces impossible values; missing sensors silently become NaN | `test_plausible_ranges_and_zero_null_contract` |
| Binary target and unique reading IDs | Label export changes to an unsupported class or ingestion duplicates events | `test_labels_and_identifiers_contract` |
| Disjoint machines across splits | The same machine leaks into training and evaluation, inflating apparent quality | `test_machine_id_split_has_no_leakage` |

Model behaviour tests check a known healthy machine scores below 0.25 and probabilities
are bounded, finite, and nonconstant. CI trains a deterministic disposable fixture. During
CD, these tests run again against the downloaded registry version through `MODEL_PATH`.
The container integration test asserts response schema, version, batch limits, 422 handling,
rolling telemetry, and non-root UID 10001. Timing is observed, not asserted as a fragile CI benchmark.

## CI/CD and identity

The repository-root `.github/workflows/lab4-ci.yml` runs lint → unit → data contract/leakage
→ behaviour/service/monitoring → SHA-tagged image build → real container integration.
Only a green **push to main** can enter staging; `LAB4_DEPLOY_ENABLED=true` explicitly
enables it. Pull requests never receive deployment credentials. The exact tested image is
transferred to CD rather than rebuilt. CD tests the registered model before push/deploy,
pushes a SHA-tagged image, deploys its immutable digest, and smoke-tests the managed endpoint.

Use GitHub's `staging` environment and Entra OIDC subject
`repo:DewPerawis/6688012-ITCS355-MLOP:environment:staging`. No client secret is needed.
`scripts.github_setup` previews federation, scoped roles, repository variables, and identity
IDs before `--execute`. Workspace Contributor and registry AcrPush are separate scopes;
refine these to custom roles if operating beyond the coursework demonstration.

If the tenant denies app registration, an existing user-assigned managed identity can
also trust the same GitHub OIDC subject. Use `scripts.github_setup --managed-identity NAME`
to preview its setup; this path uses Azure Resource Manager operations and avoids app/SP
directory lookups. Creating an identity and assigning roles still require the appropriate
Azure resource permissions. The GitHub-hosted OIDC workflow needs no Azure VM.

`scripts.bad_pr` deliberately drops `temp_c` from the generated CSV in an isolated branch
and worktree. The schema contract fails before build. Capture the real run/test/error,
then close this PR without merging. Local failure evidence is not a substitute for that PR.

## Dashboard and SLO

The service keeps bounded five-minute windows and exposes `/metrics` and `/observability`
for local checking. Structured scoring logs include UTC event time, endpoint, version, and
the six accepted synthetic feature values; request logs contain status and application latency.
Production feature logging here is limited to this synthetic sensor exercise. A system
handling private data should apply its retention and minimization requirements first.

Azure gateway traffic and container console logs flow to Log Analytics through diagnostic
settings. `monitoring/workbook.json` imports into Azure Workbooks; `monitoring/queries.kql`
contains its five panels: request rate, 4xx/5xx, gateway p50/p95/p99, rolling five-minute
temperature mean, and current model versions. `/metrics` latency is application-only;
gateway `TotalDurationMs` is a different measurement. Do not compare them as identical.

`monitoring/slo.yaml` defines availability 99.5% over 30 days, gateway p95 below 250 ms,
and monitoring freshness. Each has a response when its budget is spent. The short lab
exercise cannot demonstrate 30-day SLO compliance. Lab 3's 10-VU controlled measurement
is kept distinct from the ongoing five-minute dashboard window.

## Drift threshold and scheduled alert

The reference contains **training machines only**, never validation/test machines. PSI
uses reference quantile bins, infinite boundary bins and Laplace smoothing; KS is reported
alongside it. Constant reference features are handled explicitly instead of always appearing stable.
Calibration bootstraps complete machines because each machine contributes correlated readings.
It uses 200 null windows of 500 rows and the maximum PSI across six features; the trigger
is `max(0.10, 1.5 × null maximum-PSI p99)`. The multiplier provides a declared conservative
margin; it is a design choice, not a proven false-positive bound. This is in-sample synthetic
calibration and needs validation on independent real production windows.

The measured local threshold is recorded in `reports/threshold-calibration.json`. The
scheduled job downloads no training secrets: it receives only an allowlisted code package,
training reference, and calibration. It reads the newest 500 version-1 production feature
rows from a 15-minute Log Analytics event-time window, logs PSI/KS as Azure ML MLflow metrics,
and obtains its HTTPS webhook from Key Vault using compute managed identity. Missing or
insufficient recent data fails monitoring rather than being labelled stable.

The Azure ML pipeline has `force_rerun=true`. Its schedule runs every five minutes and
expires after two hours by default; disable it explicitly after the demonstration. A
dedicated compute cluster has min=0/max=1. Job startup and log ingestion add detection delay;
do not claim the five-minute cadence is a five-minute detection guarantee.

Replay unshifted inputs, then deliberately shift `temp_c` by +12 C while staying inside
the plausible schema. Capture a scheduled run's alert, the received notification, and the
dashboard. `scripts.finalize_evidence` computes the observed injection-to-webhook time and
writes the required five-line post-mortem. Webhook acceptance and human/channel receipt
remain separate facts. No retraining or model rollback is automatic.

## Cleanup and costs

Inspect live Azure prices/quota and billing before starting the endpoint or compute.
Azure Students credit is still consumption; the course-wide limit is below 800 THB.
No measured Lab 4 cloud cost exists yet. `reports/lab4-cost.md` records the fields to capture.

```bash
make disable-schedule
make cleanup-plan
# Only after reviewing the exact plan:
make teardown ENDPOINT_CONFIRM=itcs355-6688012-lab4
```

Cleanup checks owner/course/lab tags, refuses to delete while tagged Lab 4 jobs are active,
and verifies endpoint, schedule, and dedicated compute absence. Preserve the workspace,
Storage, ACR and registry for later labs. Remove or disable the repository's deployment
switch before teardown so later main pushes cannot recreate the endpoint.

## Submission evidence

- Source, tests, hashed locks, Dockerfiles and root workflow.
- Dashboard/queries and SLO.
- Failed GitHub run, named data contract error, closed-unmerged PR.
- SHA/digest, green staging deployment and managed smoke result.
- Enabled schedule, actual scheduled job ID, drift metrics, delivered alert and receipt.
- Injection timestamps, measured detection time, dashboard screenshot, five-line post-mortem.
- Reviewed teardown/absence evidence and actual billing observations.

Configuration, tokens, webhook URLs, raw/generated data, downloaded models, caches and
temporary image archives must not be committed. Keep measured nonsecret report evidence.

## Official implementation references

- [Azure endpoint monitoring and diagnostic logs](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-monitor-online-endpoints?view=azureml-api-2)
- [Azure console log schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/amlonlineendpointconsolelog)
- [Azure ML pipeline schedules](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-schedule-pipeline-job?view=azureml-api-2)
- [GitHub OIDC with Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure)
