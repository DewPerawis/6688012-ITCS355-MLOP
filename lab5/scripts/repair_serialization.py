"""User-run serialization repair; retain the six-step DAG without repeating setup."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone

from cloudlayer.execute import (REPORT, commit_source, endpoint_exists, job_status,
                                owned, progress, run_variant, save)
from cloudlayer.pipelines import definition
from cloudlayer.readiness import LAB, REPO, inherited_config
from scripts.resume_normal import verify_bundle


def verify_failure(state, inspection):
    if (inspection.get("job") != state["jobs"]["normal"]["name"]
            or inspection.get("source_commit") != state["source_commit"]
            or inspection.get("status") != "Failed"
            or inspection.get("no_registration") is not True
            or inspection.get("endpoint_exists") is not False):
        raise ValueError("A matching, inspected normal-training failure is required")
    steps = {child["step"]: child for child in inspection["children"]}
    if (any(steps.get(step, {}).get("status") != "Completed" for step in ("ingest", "validate"))
            or steps.get("train", {}).get("status") != "Failed"
            or any(steps.get(step, {}).get("status") in ("Running", "Completed")
                   for step in ("evaluate", "register", "deploy_staging"))):
        raise ValueError("Failure is not confined to training before evaluation/release")
    logs = "\n".join(item["tail"] for item in steps["train"].get("user_log_excerpts", []))
    if not all(token in logs for token in ("mlflow.sklearn.save_model", "Untrusted",
                                           "sklearn.tree._tree.Tree")):
        raise ValueError("The observed failure is not the reviewed MLflow serialization error")
    if not state["jobs"]["degraded"].get("expected_gate_failure_verified"):
        raise ValueError("Preserve the verified negative control before retrying")


def repair_definition(state, preview):
    doc = definition(state["runtime"], str(REPO / state["bundle"]), preview["raw_sha256"])
    # Prior jobs used force_rerun=True, so their child results cannot be reused.
    # Keep all six steps to demonstrate a complete successful managed pipeline.
    doc["settings"]["force_rerun"] = False
    doc["display_name"] = "lab5-normal-serialization-repair"
    return doc


def main():
    import yaml
    from azure.ai.ml import MLClient, load_job
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import AzureCliCredential

    state = json.loads(REPORT.read_text())
    preview = json.loads((LAB / "reports/pipeline-preview.json").read_text())
    cfg, _ = inherited_config()
    for key, field in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                       ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != state["runtime"][field].lower():
            raise ValueError("Workspace configuration differs from the existing run")
    client = MLClient(AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
                      cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
                      enable_telemetry=False)
    label = "normal-repair"
    progress("1/3 Check the inspected failure and existing resources; no setup")
    verify_bundle(state)
    try:
        client.jobs.get(state["run_prefix"] + "-" + label)
        retry_exists = True
    except ResourceNotFoundError:
        retry_exists = False
    if not retry_exists:
        if job_status(client.jobs.get(state["jobs"]["normal"]["name"]).status) != "Failed":
            raise ValueError("Original normal job is not Failed")
        versions = sorted(str(model.version) for model in client.models.list(name=state["runtime"]["model_name"]))
        if versions != state["baseline_model_versions"] or endpoint_exists(client, state["runtime"]["endpoint"]):
            raise ValueError("Registry/endpoint changed; inspect before submitting")
    for name, expected in state["compute"].items():
        compute = client.compute.get(name)
        owned(compute)
        identities = [item.resource_id.lower() for item in (compute.identity.user_assigned_identities or [])]
        if (compute.size.lower() != expected["size"].lower() or compute.min_instances != 0
                or compute.max_instances != 1 or identities != [expected["identity_id"].lower()]):
            raise ValueError("Existing compute configuration changed: " + name)
    if "serialization_repair" not in state:
        if retry_exists:
            raise ValueError("A retry exists without its local source record; inspect before continuing")
        inspection = json.loads((LAB / "reports/part5-inspection.json").read_text())
        verify_failure(state, inspection)
        history = LAB / "reports/execution-history"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copyfile(REPORT, history / (stamp + ".json"))
        original = {key: state[key] for key in ("source_commit", "runtime", "bundle", "bundle_hashes")}
        for record in state["jobs"].values():
            record.setdefault("source_commit", state["source_commit"])
        # User executes the local source commit. No push, roles or compute creation.
        progress("2/3 Commit the serialization fix locally and snapshot revised source; no push")
        source_commit = commit_source()
        destination = LAB / "_bundles" / (state["run_prefix"] + "-serialization-repair")
        destination.mkdir(parents=True, exist_ok=True)
        for relative in original["bundle_hashes"]:
            if relative == "runtime.json":
                continue
            source = LAB / relative if relative == "src/pipeline_steps.py" else REPO / original["bundle"] / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        runtime = {**original["runtime"], "source_base_commit": source_commit}
        (destination / "runtime.json").write_text(json.dumps(runtime, indent=2))
        state.update(source_commit=source_commit, runtime=runtime, bundle=destination.relative_to(REPO).as_posix(),
                     bundle_hashes={path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in destination.rglob("*") if path.is_file()})
        state["serialization_repair"] = {
            "original": original, "reason": "Explicit Lab 2 cloudpickle format for our fitted RandomForest",
            "inspection_sha256": hashlib.sha256((LAB / "reports/part5-inspection.json").read_bytes()).hexdigest(),
            "upstream_reuse": "Not expected: original pipeline had force_rerun=True"}
        save(state)
    document = repair_definition(state, preview)
    path = LAB / "reports" / (state["run_prefix"] + "-normal-repair.yaml")
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    load_job(source=path)  # Validate schema before job submission.
    state.update(active_normal_variant=label, status="repairing_serialization", cleanup_pending=True)
    state.pop("error_type", None)
    state.pop("error_message", None)
    save(state)
    try:
        progress("3/3 Submit/observe one normal-repair job; retain gate, register and staging checks")
        run_variant(client, preview, state, degraded=False, label=label, document=document)
        state["status"] = "managed_pipeline_completed"
        save(state)
    except Exception as exc:
        state.update(status="needs_attention", error_type=type(exc).__name__, error_message=str(exc)[:1000])
        save(state)
        # Return the actual failed-child error in this same notebook execution.
        try:
            from scripts.inspect_existing import main as inspect_existing
            progress("Read failure details now; no extra inspection notebook is needed")
            inspect_existing()
        except Exception as diagnostic_error:
            print("Could not fetch diagnostics: " + type(diagnostic_error).__name__, flush=True)
        raise
    finally:
        print("\n--- SEND THIS SUMMARY ---", flush=True)
        summary = {key: state[key] for key in ("status", "source_commit", "jobs", "cleanup_pending",
                                               "error_type", "error_message") if key in state}
        summary.update(setup_repeated=False, degraded_retrained=False,
                       upstream_reuse="Not expected; six-step normal pipeline is rerun with fixed serialization")
        print(json.dumps(summary, indent=2), flush=True)
        print("Send the summary. Staging may remain running and requires evidence/cleanup next.", flush=True)


if __name__ == "__main__":
    main()
