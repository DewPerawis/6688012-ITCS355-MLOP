# Lab 4 progress status — 12 October 2026 (Thailand)

This report separates verified local preparation from the cloud evidence still required.
The assistant prepared and ran local checks at the student's request. These results must
not be represented as a completed graded cloud exercise.

## Latest student-run verification — 12 October 2026 (Thailand)

The student supplied the complete output of `bash run_local_checks.sh`. Prerequisites,
fixture generation, lint/portability, all 24 tests, deliberate contract failure/restoration,
and local drift rehearsal completed. Tests took 5.52 seconds with one deprecation warning.
Preflight timestamp: `2026-10-11T19:07:55.157612+00:00` (12 October in Thailand).
The measured threshold was 0.7622300758; temperature PSI was 0.0122575881 for baseline and
1.2863608401 after the controlled +12 C shift. Real-channel alert and scheduled cloud job
flags remained false. See `user-local-checks.log` and `user-local-checks.json`.
The archived output's old "assistant local rehearsal" label was a static script label;
the output in this section was supplied by the student. The script label is now neutral.

Identity setup update: the student's Entra app-create command was denied with directory
`Insufficient privileges`. The setup helper now also supports existing user-assigned managed
identities through Resource Manager federation. Two isolated tests passed for read-only preview,
absence of directory lookups, correct staging subject and scoped roles. The CI includes these
tests. No managed identity, federation or role grant has been created by the assistant.
The original 24-test student result above predates these two additional tests.

The student subsequently supplied successful identity creation, preview, and execution output.
Identity `itcs355-6688012-lab4-ci` uses client ID `308025e6-89e3-492f-b58e-672c4b0f2ef8`
and principal ID `51d18b7b-ccbd-4088-81aa-696cea767485`. The setup command completed the
staging federation, Contributor role on the ML workspace, AcrPush role on the ACR,
GitHub staging environment, three identity-ID secrets and five configuration variables.
GitHub reported environment creation at `2026-10-11T19:55:22Z`.
`LAB4_DEPLOY_ENABLED` remains false. This is student-supplied setup evidence;
an actual GitHub Actions OIDC login and deployment have not yet been verified.

## Student-run GitHub CI evidence

Commit `fb8bef9fe067bc7cbd7112f9975599bbc22867c7` passed the main workflow:
https://github.com/DewPerawis/6688012-ITCS355-MLOP/actions/runs/38171649219
The first run failed during fixture export; explicitly selecting cloudpickle for the
CI-trained fixture corrected that export failure. The subsequent workflow succeeded.

PR #1 deliberately removed `temp_c` from the generated CSV in commit
`45ce2d99232e247a4b4d78c4f76d7228737c914e`. Run `38172414175` failed in
Data contracts and leakage: 4 failed, 1 passed, including `test_training_schema_contract`
with `training schema mismatch`. Job details confirm image build, integration and
deployment were skipped. PR #1 was CLOSED with mergedAt=null.
Evidence: `blocked-ci.log`, `blocked-ci-run.json`, `blocked-pr.json`,
`blocked-pr-closure.json`. Staging deployment and scheduled cloud drift remain outstanding.

## Verified preparation

| Check | Actual observed result | Evidence |
|---|---|---|
| One-command handoff | `bash run_local_checks.sh` completed, exit 0 | `local-verification.json`; private `assistant-check.log` |
| Unit/data/behaviour/service/monitoring suite | 24 passed, 1 warning, 4.70 seconds in the handoff run | Local check log |
| Lint and portability | Passed; provider SDK code confined to cloudlayer | Local check log |
| Deliberately broken contract | Missing temp_c caused `test_training_schema_contract` to fail; CSV restored byte-for-byte | `local-contract-failure.json` |
| Exact registry asset | Live Azure read confirmed `itcs355-6688012:1`; downloaded its artifact | `cloud-inspection.json` |
| Registered-model behaviour | 2 behaviour tests passed against version 1 | Preparation tool output; models kept private locally |
| Serving image | linux/amd64 built from pinned base and hashed lock | `local-verification.json` |
| Real container integration | 6 checks passed: readiness/version, single schema, batch, 422/batch limit, rolling telemetry, non-root UID | `registry-container-integration.json` |
| Downloaded model identity | Live-downloaded model.pkl SHA-256 matches the saved Lab 3 model used in container check | `local-verification.json` |
| Monitor image | Built; pip check clean; MLflow 3.15.0 and Azure MLflow plugin 1.62.0.post6 import/entry point passed; UID 10001 | `monitor-image-check.json` |
| Drift calibration | 200 machine-cluster bootstrap windows, 500 rows, training machines only; threshold 0.7622300758 | `threshold-calibration.json` |
| Baseline versus shifted temperature | temp_c PSI 0.0122575881 versus 1.2863608401 after +12 C; baseline stable and shifted window breached | `local-drift-rehearsal.json` |
| Azure schedule API | Pipeline serialized with force_rerun and managed-identity child; schedule/download/disable/delete SDK signatures checked locally | Preparation check output |
| Prerequisites | Python 3.11.16, existing dependencies/tools and Docker engine available | `preflight.json` |
| Git policy | Workflow/source/nonsecret evidence visible; config, models, data, private instructions and caches ignored; no staged files | Preparation Git inspection |

Known warning: FastAPI/Starlette deprecates its current httpx TestClient transport in the
existing pinned environment. It did not fail tests; no dependency migration was performed.

## Live cloud execution and remaining submission evidence

| Required artifact | Implementation ready | Actual exercise status |
|---|---|---|
| GitHub Actions full gate | `.github/workflows/lab4-ci.yml` | Main run 38171649219 succeeded |
| OIDC and scoped roles | `scripts.github_setup`, preview before execute | OIDC login passed in run 38174583649; immutable subject and ACR Reader corrections required |
| Bad PR blocked before build | `scripts.bad_pr` | PR #1 failed schema gate; build/deploy skipped; closed unmerged |
| SHA image push/staging/smoke | Workflow and Azure adapter | Run 38174583649 passed; downloaded staging-04aedd4 artifacts |
| Dashboard with five signals | Workbook JSON, KQL and service logs | Five actual Azure query results and PNG/PDF export saved; Portal screenshot is separate |
| SLO target/window/response | `monitoring/slo.yaml` | Definition ready; long-window compliance unmeasured |
| Scheduled production-input detector | Azure ML pipeline/schedule controller and managed-identity job | Actual scheduled run completed; read 500 endpoint log inputs |
| Real channel alert | Discord HTTPS transport; Key Vault lookup | HTTP 204 and actual Discord screenshots confirmed |
| Injection-to-alert interval | Replay timestamp and strict evidence finalizer | 521.911988 seconds from first injected request to webhook acceptance |
| Five-line post-mortem | Generated from measured evidence | postmortem.md and measured evidence reference the actual cloud dashboard export |
| Teardown/cost | Tag/name-checked cleanup and cost report | Endpoint, schedule and monitor compute deleted; remaining={}; billed cost still pending |

Successful scheduled pipeline:
`itcs355-6688012-lab4-drift-08584098484054611101308887078CU10`;
child `f3247490-e8ce-45b9-8212-eea464dced9d` Completed.
Actual drift artifact: status=drift, rows=500, temp_c PSI approximately 1.2185,
threshold=0.7622300758, webhook HTTP=204. Discord receipt at 05:45 on 12 October 2026
Thailand time is saved in `discord-drift-alert.png` and `discord-drift-alerts.png`.
The first scheduled attempts reached delivery but failed with HTTP 403; adding the
documented Discord User-Agent and Discord content payload allowed delivery.
The separate channel setup test is not counted as scheduled drift evidence.

Teardown verified at 2026-10-11T23:01:17.708420Z (06:01:17 on 12 October, Thailand).
`lab4-teardown.json` confirms no remaining Lab 4 endpoint, schedule or monitor compute.
Workspace, ACR, Storage, model registry, Key Vault and workbook remain for later work.
This does not establish zero residual storage, registry or logging charges.

The five-panel dashboard export is labelled as actual retained Azure log data, not a
Portal screenshot. `dashboard-cloud-data.json` records all queries and observed rows;
`dashboard-cloud-evidence.png` and `.pdf` display the shift. Historical workbook JSON
pins the experiment window. Source edits and evidence still need a reviewed final commit/push.
Retail price references and three posted shared-resource cost rows are captured; recent
compute charges are absent, so final billing reconciliation remains pending.

## What was changed on the owner's machine

Added the isolated `lab4/` implementation and root Lab 4 workflow. Updated only the
machine-local ignored root `.gitignore` for Lab 4 secrets, generated data/models, private
instructions and temporary worktrees. Earlier labs and `pj/` were not edited.
Built two local Docker images and stopped temporary integration containers. No cloud
endpoint/compute/schedule was created, no registry model was promoted, and no Git commit,
push, PR or outgoing notification was performed.

## Start after waking up

Use Ubuntu/WSL, enter `lab4/`, and run `bash run_local_checks.sh`. Send its output to the
assistant and follow the private `START_HERE_TH.md` checkpoints. User-run cloud and GitHub
evidence is required before changing the submission status to completed.
