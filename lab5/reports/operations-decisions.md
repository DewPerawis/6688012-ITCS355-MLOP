# Lab 5 identity and retraining decisions

## Identity inventory from recorded execution

| Identity | Recorded permission | Reason and limitation |
|---|---|---|
| lab5-train | Contributor on itcs355 data/artifact container; Reader on default container; AcrPull | Read versioned inputs, write outputs and pull the immutable image |
| lab5-serve | AcrPull; Blob Data Reader on workspace Storage account after correction | Download serving image and model/startup manifest; initial one-container Reader was insufficient |
| existing lab4-ci | Artifact-container Contributors, Managed Identity Operator on serving UAI; existing workspace Contributor and ACR access | Register/deploy using a separate release identity; existing workspace Contributor is broader than a custom least-privilege role |

Serving reads at account scope, including shared containers: this is a documented access
boundary, not a claim of minimum possible data exposure. No role-withdrawal experiment
was performed. Initially missing a permission, observing a 403 and granting it is not
equivalent to deliberately removing a permission and testing the result.

## Retraining strategy for machine sensor failure prediction

This is the written design comparison required by Task 3. No deployed schedule is claimed.

| Strategy | Appropriate use here | Failure mode |
|---|---|---|
| Fixed weekly review | Predictable review of new sensor rows with confirmed maintenance/failure labels; retrain only when enough independent machine groups exist | Wastes jobs if labels/data are unchanged; can miss a rapid operating-regime change |
| New labelled data volume | Wait for meaningful new machine groups rather than repeated correlated readings from one machine | A busy single machine can inflate row counts; delayed failure labels can stop retraining indefinitely |
| Drift-triggered review | Feature drift signals sensor/load changes for investigation, followed by validated labelled-data review | A faulty sensor or unit conversion can trigger training on corrupted inputs and damage a working model |

Proposed choice: a weekly eligibility check with labelled-data and machine-group checks,
plus drift alerts for early human review. A trigger must not bypass hash/schema/range/
class/group-leakage contracts, validation gate or lineage. If upstream data are corrupted,
stop and repair ingestion; do not retrain just because a drift score is high. Keep the
incumbent unless the validation gate passes. The single-seed margin remains an operational
guard rather than proof of stable improvement.

A live schedule, its identity, an execution and cleanup of that schedule still require
user-run cloud evidence. No schedule was created solely to make the report look complete.
