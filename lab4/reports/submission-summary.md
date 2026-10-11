# Lab 4 submission evidence — 6688012

The cloud exercise completed on 12 October 2026, Thailand time. Implementation and evidence
were published in commit `d9b23e8`; final CI run `38183928346` completed successfully with
deployment skipped. The handout's 12 deliverables are mapped below and checked in README.
Cost Management reconciliation must be refreshed after
Azure posts the recent compute usage; the current billing snapshot is not a final Lab 4 bill.

| Requirement | Actual evidence |
|---|---|
| Unit, data, leakage, model and integration tests | 28 local tests passed; real image integration passed in main CI and against registry model version 1 during CD |
| Incident explanations | README names dropped features, wrong units/ranges, missing values, invalid labels, duplicate identifiers and machine leakage |
| CI gates | Main run 38171649219 passed; full CI/CD run 38174583649 subsequently passed |
| Blocked bad commit | PR #1; run 38172414175; test_training_schema_contract; training schema mismatch; image build/deploy skipped; PR closed unmerged |
| SHA image and staging | image-push.json and lab4-deployment.json; model itcs355-6688012:1; serving image tagged 04aedd4 full SHA and pinned by digest |
| Identity federation | Azure login succeeded; immutable GitHub subject; workspace Contributor and ACR AcrPush/Reader at resource scopes |
| Five-signal dashboard | monitoring/workbook.json; workbook-evidence.json; dashboard-cloud-data.json; dashboard-cloud-evidence.png/pdf |
| SLO | monitoring/slo.yaml states target, window and error-budget response; this short exercise does not prove 30-day compliance |
| Baseline | cloud-baseline.json: stable; 500 rows; temp_c PSI 0.01305214; no alert |
| Scheduled drift | scheduled-run.json proves Schedule source and Completed; cloud-drift.json records 500 rows and PSI 1.21851169 versus threshold 0.76223008 |
| Actual alert receipt | Discord HTTP 204; discord-drift-alert.png and discord-drift-alerts.png show actual messages |
| Detection interval | injected-drift-evidence.json: injection to webhook acceptance 521.911988 seconds; detection to HTTP acceptance 7.707207 seconds |
| Post-mortem | postmortem.md has five lines; restore corrupted input producer, keep the registered model, do not retrain on the +12 C error |
| Teardown | lab4-teardown.json and final-cloud-check.json: endpoint, schedule and monitor compute absent |
| Cost observations | retail-prices.json, billing-observation.json, cost-estimate.json and lab4-cost.md; compute bill still pending |

## Dashboard provenance

The dashboard figure is rendered from five actual retained Log Analytics query results.
It is not presented as an Azure Portal screenshot. It shows the observed temperature
mean shift from about 79 C to 91 C, historical model version 1, batch request rate,
observed 4xx/5xx fractions and gateway p50/p95/p99. Only observed bins are plotted.
The exported window also includes the earlier injected replay whose Discord delivery
failed with HTTP 403; the final successful injection is marked separately.
The finalizer identifies dashboard_evidence_kind=data_export.

The Portal workbook was configured during the experiment. For a Portal screenshot,
import monitoring/workbook-evidence.json within its last-24-hour query scope and capture
the five graphs; the endpoint is not needed because logs are retained. The offline PNG/PDF
can be reproduced later from saved dashboard-cloud-data.json without any cloud calls.

## Runtime corrections

CI fixture export was made explicit as cloudpickle. GitHub's immutable subject IDs were
matched in Azure federation. Reader was added on the ACR so the CI identity could discover
the registry in addition to pushing images. Initial log ingestion delayed readiness.
Scheduled delivery initially failed with HTTP 403; the documented Discord User-Agent
and Discord-specific content payload corrected delivery. A channel setup test remains
distinct from actual scheduled drift evidence.

## Publication boundary

submission-files.txt allowlists source and nonsecret measured evidence. It excludes cloud.env,
webhook URL files, raw/generated data, downloaded models and full cloud system/debug logs.
Workspace, Storage, ACR, Key Vault, registry and workbook remain for later coursework.
The three billable Lab 4 compute/schedule resources were removed; residual storage,
registry and log retention charges are not claimed to be zero.
