# Lab 5 managed execution evidence

Student: 6688012. Evidence comes from the student's recorded Azure runs on 23 October 2026.
This report is a local summary of those results, not a new cloud inspection.

| Stage | Recorded result |
|---|---|
| Data ingest and validation | Completed in normal-repair; deterministic grouped split 3600/1200/1200 |
| Training | Completed, run `f115d4dd-f69c-4195-8c1c-f4a87f9bbf3d` |
| Evaluation | Completed; validation PR-AUC 0.40244651283160715 |
| Registration | Completed; model `itcs355-6688012:3` |
| Deployment continuation | `lab5-20261023-070538-deploy-repair-v2` Completed |
| Endpoint smoke | model_version 3; probability 0.005104794545095873 |
| Test PR-AUC | 0.48110817994638944; not used for candidate selection |

## Gate and lineage

Incumbent v1 validation PR-AUC: 0.40004728306048276. Floor: 0.4; required delta: 0.002.
The measured candidate passes this operational guard. One seed does not demonstrate a stable gain.
The real degraded run measured validation PR-AUC 0.10083333333333333 and failed at evaluate,
with no new registration or endpoint at its inspection.

Model training source: `4f3a8957ded20901989fa48bbe58be29c33f6578`.
Estimate commit: `83c400d616b3323c292d9c028fd80cfd9e1200ba`. Data version: `1c886b512c8a5c9bf723da1cd119fc80.dir`.
Original registration child: `c528322e-0d8a-4860-b7e4-c2f8fdde4de2`.

## Recovery and limitations

The original six-step normal-repair parent remains Failed. Its first five steps completed;
the deployment was completed in a separate managed continuation. This is a working recovered
service, not evidence of one successful six-step triggered execution as Task 1 requests.
No training or model registration was repeated during the successful deployment continuation.

The initial serving identity had Reader only on a blob container. Startup needed workspace
storage-account access. The reviewed account-level Reader grant fixed that scope gap; AcrPull
was already present. This missing-role incident is not the required deliberate permission-removal
experiment. A later continuation also failed on cross-job URI resolution before release code ran;
the successful job packages the verified model reference with the frozen runtime instead.

Canonical evidence: `managed-execution.json`; role/model audit: `deployment-audit.json`;
original failure inspection: `part5-inspection.json`; deployment YAML: `lab5-20261023-070538-deploy-repair-v2.yaml`.
Source bundle hashes and exact run IDs are retained in the canonical state.

## Remaining live evidence

Capture Portal/Studio screenshots. Run the separately prepared runtime cleanup only after
reviewing its three deletion targets. Model, image and job history are retained for inspection.
Final billed cost and the check 24 hours after teardown remain pending.
