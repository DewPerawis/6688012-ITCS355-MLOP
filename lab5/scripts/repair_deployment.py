"""User-run: one scoped Blob Reader grant and a deployment-only managed job.

Retains the registered model and frozen runtime; no training, registration or Git changes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cloudlayer.endpoint_checks import role_evidence
from cloudlayer.execute import REPORT, job_status, owned, progress, save, wait_job
from cloudlayer.pipelines import definition
from cloudlayer.readiness import LAB, REPO, cli_json, inherited_config
from scripts.inspect_deployment import main as inspect_deployment, reference
from scripts.inspect_existing import main as inspect_job
from scripts.resume_normal import verify_bundle
from src.pipeline_steps import decision


def verified_candidate(audit, state):
    original = state["jobs"]["normal-repair"]
    model = audit["registered_model"]
    steps = {item["step"]: item for item in audit["steps"]}
    if (audit["job"] != original["name"] or audit["source_commit"] != original["source_commit"]
            or any(steps.get(step, {}).get("status") != "Completed"
                   for step in ("ingest", "validate", "train", "evaluate", "register"))
            or steps.get("deploy_staging", {}).get("status") != "Failed"):
        raise ValueError("Audit does not confirm the completed steps of this original pipeline")
    tags = model["lineage"]
    if (model["name"] != state["runtime"]["model_name"]
            or str(model["version"]) != audit["deployment"]["model_version"]
            or tags.get("git_commit") != original["source_commit"]
            or tags.get("training_job_id") != steps["train"]["name"]
            or tags.get("estimate_commit") != state["estimate_commit"]
            or not decision(float(tags["metric_val"]), state["runtime"]["incumbent_metric"])):
        raise ValueError("Registered candidate/version/lineage/gate is inconsistent")
    if (not audit["endpoint"]["expected_identity_attached"] or not audit["deployment"]["image_matches_pinned"]
            or audit["permission_checks"]["registry_pull"].get("verified_unconditional_role") is not True
            or audit["permission_checks"]["workspace_storage_reader"].get("status") != "ok"):
        raise ValueError("Identity, pinned image or required permission inventory is unverified")
    return model, steps["register"]["name"]


def deployment_definition(state, preview, code=None):
    document = definition(state["runtime"], str(code or REPO / state["bundle"]), preview["raw_sha256"])
    node = copy.deepcopy(document["jobs"]["deploy_staging"])
    node["inputs"] = {}
    node["command"] = node["command"].replace("${{inputs.registered}}", "./registered")
    document["jobs"] = {"deploy_staging": node}
    document["settings"]["force_rerun"] = True
    document["display_name"] = "lab5-deployment-continuation"
    return document


def current_roles(runtime, principal, scope):
    return cli_json(["role", "assignment", "list", "--subscription", runtime["subscription"],
                     "--scope", scope, "--include-inherited", "--assignee-object-id", principal,
                     "--fill-principal-name", "false",
                     "--query", "[].{id:id,principalId:principalId,roleDefinitionName:roleDefinitionName,scope:scope,condition:condition}"])


def registered_reference(job, expected_name, candidate):
    # Persist the independently audited registry reference, not a cross-job URI.
    if job.name != expected_name or job_status(job.status) != "Completed":
        raise ValueError("Original registration job does not match or is not Completed")
    return {"name": candidate["name"], "version": str(candidate["version"]),
            "lineage": candidate["lineage"], "origin_registration_job": expected_name}


def main():
    import yaml
    from azure.ai.ml import MLClient, load_job
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import AzureCliCredential

    state = json.loads(REPORT.read_text())
    audit_path = LAB / "reports/deployment-audit.json"
    # Preserve the reviewed audit even when later diagnostics refresh deployment-audit.json.
    continuation = state.get("deployment_continuation")
    audit = continuation["reviewed_audit"] if continuation else json.loads(audit_path.read_text())
    candidate, register_job_name = verified_candidate(audit, state)
    verify_bundle(state)
    cfg, _ = inherited_config()
    runtime = state["runtime"]
    for key, field in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                       ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != runtime[field].lower():
            raise ValueError("Current workspace differs from the reviewed audit")
    client = MLClient(AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
                      cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
                      enable_telemetry=False)
    label = "deploy-repair-v2"
    name = state["run_prefix"] + "-" + label
    progress("1/4 Recheck the exact model, endpoint identity, compute and role scopes")
    endpoint = client.online_endpoints.get(runtime["endpoint"])
    deployment = client.online_deployments.get(name="staging", endpoint_name=endpoint.name)
    owned(endpoint)
    owned(deployment)
    attached = [item.resource_id.lower() for item in (endpoint.identity.user_assigned_identities or [])]
    if attached != [runtime["serve_identity_id"].lower()]:
        raise ValueError("Endpoint identity changed since audit")
    version = str(candidate["version"])
    expected_model = audit["deployment"]["model"]
    if (reference(deployment.model) != expected_model
            or (deployment.environment_variables or {}).get("MODEL_VERSION") != version
            or (deployment.environment_variables or {}).get("MODEL_PATH") != audit["deployment"]["model_path"]
            or deployment.instance_type != audit["deployment"]["instance_type"]
            or deployment.instance_count != 1):
        raise ValueError("Existing deployment model/mount/size changed since audit")
    if reference(deployment.environment) != audit["deployment"]["environment"]:
        raise ValueError("Deployment environment changed since audit")
    model = client.models.get(name=candidate["name"], version=version)
    if (any((model.tags or {}).get(key) != value for key, value in candidate["lineage"].items())
            or reference(model.path) != candidate["path"]):
        raise ValueError("Registered model metadata changed since audit")
    workspace = client.workspaces.get(runtime["workspace"])
    storage_scope = reference(workspace.storage_account)
    registry_scope = reference(workspace.container_registry)
    if (storage_scope.lower() != audit["workspace_resources"]["storage_account"].lower()
            or registry_scope.lower() != audit["workspace_resources"]["container_registry"].lower()):
        raise ValueError("Workspace storage/registry changed since audit")
    identity = cli_json(["identity", "show", "--ids", runtime["serve_identity_id"],
                         "--subscription", runtime["subscription"], "--query", "{principalId:principalId}"])
    principal = identity["principalId"]
    if principal != audit["serving_identity"]["principalId"]:
        raise ValueError("Serving identity principal changed since audit")
    acr_roles = current_roles(runtime, principal, registry_scope)
    if not role_evidence(acr_roles, principal, registry_scope, {"AcrPull", "AcrPush"})["verified_unconditional_role"]:
        raise ValueError("Existing AcrPull access is no longer verified; no additional roles will be granted")
    for compute_name, expected in state["compute"].items():
        compute = client.compute.get(compute_name)
        owned(compute)
        attached = [item.resource_id.lower() for item in (compute.identity.user_assigned_identities or [])]
        if (compute.size.lower() != expected["size"].lower() or compute.min_instances != 0
                or compute.max_instances != 1 or attached != [expected["identity_id"].lower()]):
            raise ValueError("Compute configuration changed: " + compute_name)
    registered_job = client.jobs.get(register_job_name)
    registered = registered_reference(registered_job, register_job_name, candidate)
    code = LAB / "_bundles" / name
    code.mkdir(parents=True, exist_ok=True)
    # Copy the verified frozen runtime; never modify the original training bundle.
    for relative in state["bundle_hashes"]:
        target = code / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / state["bundle"] / relative, target)
    (code / "registered").mkdir(exist_ok=True)
    (code / "registered/registered.json").write_text(json.dumps(registered, indent=2))
    preview = json.loads((LAB / "reports/pipeline-preview.json").read_text())
    document = deployment_definition(state, preview, code)
    yaml_path = LAB / "reports" / (name + ".yaml")
    yaml_path.write_text(yaml.safe_dump(document, sort_keys=False))
    parsed_job = load_job(source=yaml_path)  # Check schema before any role or deployment mutation.
    parsed_job.name = name
    parsed_job.tags.update(git_commit=state["source_commit"], estimate_commit=state["estimate_commit"],
                           model_version=version, continuation_of=audit["job"])
    try:
        existing_job = client.jobs.get(name)
    except ResourceNotFoundError:
        existing_job = None
    if not continuation:
        state["deployment_continuation"] = {
            "reviewed_audit": audit, "model": {"name": candidate["name"], "version": version},
            "original_parent_status": "Failed", "registered_input": "audited registry reference in source bundle",
            "model_versions_before": sorted(str(item.version) for item in client.models.list(name=candidate["name"])),
            "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    record = state.setdefault("jobs", {}).setdefault(label, {"name": name, "source_commit": state["source_commit"]})
    record["code_bundle"] = code.relative_to(REPO).as_posix()
    record["code_bundle_hashes"] = {path.relative_to(code).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in code.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    record["registered_reference"] = registered
    state.update(active_normal_variant=label, cleanup_pending=True, status="repairing_deployment_only")
    state.pop("error_type", None)
    state.pop("error_message", None)
    save(state)
    try:
        if existing_job is None:
            progress("2/4 Add only the reviewed Storage Blob Data Reader role if absent")
            assignments = current_roles(runtime, principal, storage_scope)
            accepted = {"Storage Blob Data Reader", "Storage Blob Data Contributor", "Storage Blob Data Owner"}
            has_reader = role_evidence(assignments, principal, storage_scope, accepted)["verified_unconditional_role"]
            if not has_reader:
                assignment_name = str(uuid.uuid5(uuid.NAMESPACE_URL, storage_scope.lower() + principal + "lab5-blob-reader"))
                granted = cli_json(["role", "assignment", "create", "--subscription", runtime["subscription"],
                                    "--assignee-object-id", principal, "--assignee-principal-type", "ServicePrincipal",
                                    "--role", "Storage Blob Data Reader", "--scope", storage_scope, "--name", assignment_name,
                                    "--query", "{id:id,principalId:principalId,roleDefinitionId:roleDefinitionId,scope:scope}"])
                state["deployment_continuation"]["role_correction"] = granted
                save(state)
            assignments = current_roles(runtime, principal, storage_scope)
            if not role_evidence(assignments, principal, storage_scope, accepted)["verified_unconditional_role"]:
                raise RuntimeError("Reader role is not visible yet; no deployment job submitted. Send summary")
            # Listing RBAC is not a token/data-plane probe. Allow propagation before startup.
            for remaining in (range(90, 0, -15) if not has_reader else ()):
                progress(f"Role propagation allowance: {remaining}s; no new compute started yet")
                time.sleep(15)
            progress("3/4 Submit deployment-only continuation using the existing registered model " + version)
            client.jobs.create_or_update(parsed_job)
            record["submitted_at"] = datetime.now(timezone.utc).isoformat()
            save(state)
        else:
            progress("3/4 Observe the existing deployment-only job; do not submit again")
        job = wait_job(client, name, state, record)
        if job_status(job.status) != "Completed":
            raise RuntimeError("Deployment-only continuation failed; original model/training remain retained")
        progress("4/4 Verify deployment state, exact model version and direct scoring response")
        final = client.online_deployments.get(name="staging", endpoint_name=endpoint.name)
        if str(getattr(final.provisioning_state, "value", final.provisioning_state)).rsplit(".", 1)[-1].lower() != "succeeded":
            raise RuntimeError("Managed job completed but staging is not Succeeded")
        if reference(final.model) != expected_model:
            raise RuntimeError("Staging is bound to a different registered model")
        request = LAB / "reports/deployment-smoke-request.json"
        request.write_text(json.dumps({"temp_c": 80.0, "vibration_mm_s": 3.0, "pressure_kpa": 320.0,
                                       "hours_since_service": 2000.0, "load_pct": 70.0, "ambient_humidity": 58.0}))
        response = json.loads(client.online_endpoints.invoke(endpoint_name=endpoint.name, deployment_name="staging",
                                                             request_file=str(request)))
        probability = response.get("probability")
        if (str(response.get("model_version")) != version or isinstance(probability, bool)
                or not isinstance(probability, (int, float)) or not 0 <= probability <= 1):
            raise RuntimeError("Staging returned an unexpected model version or invalid prediction")
        versions = sorted(str(item.version) for item in client.models.list(name=candidate["name"]))
        if versions != state["deployment_continuation"]["model_versions_before"]:
            raise RuntimeError("Registry versions changed during deployment-only repair; inspect before claiming completion")
        record.update(model_version=version, smoke_passed=True, response=response)
        state["status"] = "staging_recovered_with_deployment_continuation"
        save(state)
    except Exception as exc:
        state.update(status="needs_attention", error_type=type(exc).__name__, error_message=str(exc)[:1000])
        save(state)
        try:
            if record.get("submitted_at") or existing_job is not None:
                inspect_job()
            inspect_deployment()
        except Exception as diagnostic_error:
            print("Additional diagnostics unavailable: " + type(diagnostic_error).__name__, flush=True)
        raise
    finally:
        print("\n--- SEND THIS SUMMARY ---", flush=True)
        print(json.dumps({"status": state["status"], "job": record, "model_version": version,
                          "original_pipeline": {"name": audit["job"], "status": "Failed"},
                          "training_started": False, "registration_started": False, "setup_repeated": False,
                          "cleanup_pending": True, "error": state.get("error_message"),
                          "role_correction": state["deployment_continuation"].get("role_correction")}, indent=2), flush=True)
        print("Send this summary. Staging may remain billable; evidence and cleanup follow.", flush=True)


if __name__ == "__main__":
    main()
