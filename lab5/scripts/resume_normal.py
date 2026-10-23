"""Continue only the normal pipeline after inspected, genuine negative-gate evidence.

No setup, resource/role creation, Git commit or degraded-training submission.
The existing frozen bundle and deterministic normal-job name are retained.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone

from cloudlayer.execute import REPORT, endpoint_exists, job_status, owned, progress, run_variant, save
from cloudlayer.readiness import LAB, REPO, inherited_config
from src.pipeline_steps import decision


def inspected_gate(inspection, state):
    if (inspection.get("job") != state["jobs"]["degraded"]["name"]
            or inspection.get("source_commit") != state["source_commit"]
            or inspection.get("status") != "Failed" or inspection.get("no_registration") is not True
            or inspection.get("endpoint_exists") is not False):
        raise ValueError("Inspection does not verify this execution's negative-control boundary")
    statuses = {child["step"]: child["status"] for child in inspection["children"]}
    if any(statuses.get(step) != "Completed" for step in ("ingest", "validate", "train")):
        raise ValueError("Negative job did not reach evaluation after successful training")
    if statuses.get("evaluate") != "Failed" or any(
        statuses.get(step) in ("Running", "Completed") for step in ("register", "deploy_staging")
    ):
        raise ValueError("Negative job was not blocked at the registration gate")
    gate = next(child for child in inspection["children"] if child["step"] == "evaluate")
    for excerpt in gate.get("user_log_excerpts", []):
        for line in excerpt["tail"].splitlines():
            try:
                measured = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(measured, dict) or "measured_val_pr_auc" not in measured:
                continue
            if (measured.get("passed") is not False or measured.get("deliberate_degradation") is not True
                    or measured["measured_val_pr_auc"] != measured["evaluated_val_pr_auc"]
                    or decision(measured["measured_val_pr_auc"], measured["incumbent"],
                                measured["floor"], measured["margin"])):
                raise ValueError("Measured negative-gate evidence is inconsistent")
            return measured
    raise ValueError("A measured negative-gate log is required; status alone is insufficient")


def verify_bundle(state):
    root = (REPO / state["bundle"]).resolve()
    if not root.is_relative_to((LAB / "_bundles").resolve()):
        raise ValueError("Bundle path is outside the expected local source directory")
    for relative, expected in state["bundle_hashes"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen runtime bundle changed: " + relative)
    if json.loads((root / "runtime.json").read_text()) != state["runtime"]:
        raise ValueError("Runtime identifiers differ from the submitted bundle")
    subprocess.run(["git", "diff", "--quiet", state["source_commit"], "--", "lab5/cloudlayer/pipelines.py"],
                   cwd=REPO, check=True)


def main():
    from azure.ai.ml import MLClient
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import AzureCliCredential

    state = json.loads(REPORT.read_text())
    inspection = json.loads((LAB / "reports/part5-inspection.json").read_text())
    preview = json.loads((LAB / "reports/pipeline-preview.json").read_text())
    progress("1/3 Verify inspected gate failure and the unchanged runtime bundle")
    measured = inspected_gate(inspection, state)
    verify_bundle(state)
    cfg, _ = inherited_config()
    for key, field in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                        ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != state["runtime"][field].lower():
            raise ValueError("Configuration no longer matches the existing execution")
    client = MLClient(AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
                      cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
                      enable_telemetry=False)
    progress("2/3 Read existing job/resources; skip identity, role and compute setup")
    existing = client.jobs.get(state["jobs"]["degraded"]["name"])
    if job_status(existing.status) != "Failed":
        raise ValueError("Existing negative-control job has an unexpected status")
    normal_name = state["run_prefix"] + "-normal"
    try:
        client.jobs.get(normal_name)
        normal_exists = True
    except ResourceNotFoundError:
        normal_exists = False
    if not normal_exists:
        versions = sorted(str(model.version) for model in client.models.list(name=state["runtime"]["model_name"]))
        if versions != state["baseline_model_versions"] or endpoint_exists(client, state["runtime"]["endpoint"]):
            raise ValueError("Registry/endpoint changed before the normal job; inspect rather than overwrite")
    for name, expected in state["compute"].items():
        compute = client.compute.get(name)
        owned(compute)
        attached = [item.resource_id.lower() for item in (compute.identity.user_assigned_identities or [])]
        if (compute.size.lower() != expected["size"].lower() or compute.min_instances != 0
                or compute.max_instances != 1 or attached != [expected["identity_id"].lower()]):
            raise ValueError("Existing compute/identity changed: " + name)
    history = LAB / "reports/execution-history"
    history.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    shutil.copyfile(REPORT, history / (stamp + ".json"))
    record = state["jobs"]["degraded"]
    record.update(status="Failed", expected_gate_failure_verified=True,
                  measured_gate=measured, no_registration=True, no_endpoint=True,
                  steps=[{"name": child["name"], "display_name": child["step"], "status": child["status"]}
                         for child in inspection["children"]],
                  inspection_sha256=hashlib.sha256((LAB / "reports/part5-inspection.json").read_bytes()).hexdigest())
    state.pop("error_type", None)
    state.pop("error_message", None)
    state["status"] = "resuming_normal_only"
    state["controller_resume_sha256"] = hashlib.sha256((LAB / "cloudlayer/execute.py").read_bytes()).hexdigest()
    save(state)
    try:
        progress("3/3 Run/observe normal pipeline only: " + normal_name)
        run_variant(client, preview, state, degraded=False)
        state["status"] = "managed_pipeline_completed"
        state["cleanup_pending"] = True
        save(state)
    except Exception as exc:
        state["status"] = "needs_attention"
        state["error_type"] = type(exc).__name__
        state["error_message"] = str(exc)[:1000]
        state["cleanup_pending"] = True
        save(state)
        raise
    finally:
        summary = {key: state[key] for key in ("status", "source_commit", "estimate_commit", "jobs",
                                              "cleanup_pending", "error_type", "error_message") if key in state}
        summary["setup_repeated"] = False
        summary["degraded_retrained"] = False
        print("\n--- SEND THIS SUMMARY ---", flush=True)
        print(json.dumps(summary, indent=2), flush=True)
        print("Send the summary. Existing staging/resources may remain; do not submit another job.", flush=True)


if __name__ == "__main__":
    main()
