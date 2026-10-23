"""Read the existing staging failure, identity, effective roles and model binding.

No setup, roles, training, submission, deployment update, invocation or deletion.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from cloudlayer.endpoint_checks import role_evidence
from cloudlayer.execute import job_status, owned
from cloudlayer.readiness import LAB, cli_json, inherited_config
from scripts.inspect_existing import safe_text
from scripts.preflight import progress


def reference(value):
    if value is None or isinstance(value, str):
        return value
    return getattr(value, "id", None)


def main():
    from azure.ai.ml import MLClient
    from azure.identity import AzureCliCredential

    state = json.loads((LAB / "reports/managed-execution.json").read_text())
    runtime = state["runtime"]
    cfg, _ = inherited_config()
    for key, field in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                       ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != runtime[field].lower():
            raise ValueError("Current workspace does not match the submitted job")
    client = MLClient(AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
                      cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
                      enable_telemetry=False, connection_timeout=20, read_timeout=60, retry_total=1)
    progress("1/4 Read existing pipeline, endpoint, deployment and workspace; no changes")
    variant = state.get("active_normal_variant", "normal-repair")
    record = state["jobs"][variant]
    parent = client.jobs.get(record["name"])
    children = list(client.jobs.list(parent_job_name=record["name"]))
    endpoint = client.online_endpoints.get(runtime["endpoint"])
    owned(endpoint)
    deployment = client.online_deployments.get(name="staging", endpoint_name=runtime["endpoint"])
    owned(deployment)
    workspace = client.workspaces.get(runtime["workspace"])
    storage_scope = reference(workspace.storage_account)
    registry_scope = reference(workspace.container_registry)
    if not storage_scope or not registry_scope:
        raise ValueError("Workspace storage/registry resource IDs are unavailable")
    identity = cli_json(["identity", "show", "--ids", runtime["serve_identity_id"],
                         "--subscription", runtime["subscription"],
                         "--query", "{id:id,principalId:principalId,clientId:clientId}"])
    endpoint_identity = getattr(endpoint, "identity", None)
    attached = [item.resource_id for item in (getattr(endpoint_identity, "user_assigned_identities", None) or [])]
    principal = identity["principalId"]
    report = {"inspected_at": datetime.now(timezone.utc).isoformat(),
              "status": "deployment_audit", "job": record["name"], "job_status": job_status(parent.status),
              "source_commit": record.get("source_commit", state["source_commit"]),
              "steps": [{"name": item.name, "step": item.display_name, "status": job_status(item.status)}
                        for item in children],
              "endpoint": {"name": endpoint.name, "state": str(endpoint.provisioning_state),
                           "auth_mode": endpoint.auth_mode, "identity_type": str(getattr(endpoint_identity, "type", None)),
                           "attached_user_identities": attached,
                           "expected_identity_attached": [item.lower() for item in attached]
                           == [runtime["serve_identity_id"].lower()], "traffic": endpoint.traffic},
              "serving_identity": identity,
              "deployment": {"name": deployment.name, "state": str(deployment.provisioning_state),
                             "model": reference(deployment.model), "environment": reference(deployment.environment),
                             "instance_type": deployment.instance_type, "instance_count": deployment.instance_count,
                             "model_path": (deployment.environment_variables or {}).get("MODEL_PATH"),
                             "model_version": (deployment.environment_variables or {}).get("MODEL_VERSION"),
                             "data_collector_configured": getattr(deployment, "data_collector", None) is not None},
              "workspace_resources": {"storage_account": storage_scope, "container_registry": registry_scope},
              "cloud_mutations": False, "jobs_submitted": False, "training_started": False}
    environment = deployment.environment
    if isinstance(environment, str):
        match = re.search(r"/environments/([^/]+)/versions/([^/]+)$", environment)
        if match:
            try:
                environment = client.environments.get(name=match.group(1), version=match.group(2))
            except Exception as exc:
                report["deployment"]["environment_read_error"] = type(exc).__name__
    report["deployment"]["image"] = getattr(environment, "image", None)
    report["deployment"]["image_matches_pinned"] = getattr(environment, "image", None) == runtime["serving_image"]
    report["deployment"]["inference_config"] = getattr(environment, "inference_config", None)
    progress("2/4 Read serving identity roles at storage account and ACR, including inherited roles")
    report["permission_checks"] = {}
    requirements = (("workspace_storage_reader", storage_scope,
                     {"Storage Blob Data Reader", "Storage Blob Data Contributor", "Storage Blob Data Owner"}),
                    ("registry_pull", registry_scope, {"AcrPull", "AcrPush"}))
    for label, scope, accepted in requirements:
        try:
            assignments = cli_json(["role", "assignment", "list", "--subscription", runtime["subscription"],
                                    "--scope", scope, "--include-inherited", "--assignee-object-id", principal,
                                    "--fill-principal-name", "false",
                                    "--query", "[].{id:id,principalId:principalId,roleDefinitionName:roleDefinitionName,scope:scope,condition:condition}"])
            result = role_evidence(assignments, principal, scope, accepted)
            report["permission_checks"][label] = {"status": "ok", "resource_scope": scope, **result}
        except Exception as exc:
            report["permission_checks"][label] = {"status": "unavailable", "error_type": type(exc).__name__}
    progress("3/4 Read the registered candidate's exact version, lineage and artifact path")
    version = report["deployment"]["model_version"]
    if version:
        model = client.models.get(name=runtime["model_name"], version=str(version))
        fields = ("git_commit", "data_version", "mlflow_run_id", "training_job_id", "image_digest",
                  "seed", "metric_val", "metric_test", "promotion_stage", "estimate_commit")
        report["registered_model"] = {"name": model.name, "version": str(model.version), "path": reference(model.path),
                                      "lineage": {key: value for key, value in (model.tags or {}).items() if key in fields}}
    else:
        report["registered_model"] = {"status": "unavailable", "reason": "Deployment has no MODEL_VERSION"}
    progress("4/4 Read storage-initializer/inference logs and current compute nodes")
    report["container_logs"] = {}
    # SDK 1.35 runtime validation requires hyphenated values, despite API docs
    # that list StorageInitializer / InferenceServer. Keep the observed wire names.
    for container in ("storage-initializer", "inference-server"):
        try:
            logs = client.online_deployments.get_logs(name="staging", endpoint_name=endpoint.name,
                                                      lines=80, container_type=container)
            report["container_logs"][container] = {"status": "ok", "tail": safe_text(logs)[-10000:]}
        except Exception as exc:
            report["container_logs"][container] = {"status": "unavailable", "error_type": type(exc).__name__,
                                                   "message": safe_text(str(exc))[:1200]}
    report["compute_nodes"] = {}
    for name in ("lab5train", "lab5release"):
        try:
            report["compute_nodes"][name] = {"count": len(list(client.compute.list_nodes(name=name)))}
        except Exception as exc:
            report["compute_nodes"][name] = {"status": "unavailable", "error_type": type(exc).__name__}
    report["proposed_role_correction"] = [
        {"principal_id": principal, "role": "Storage Blob Data Reader" if label == "workspace_storage_reader" else "AcrPull",
         "scope": item["resource_scope"], "applied": False}
        for label, item in report["permission_checks"].items()
        if item.get("status") == "ok" and not item["verified_unconditional_role"]]
    report["limits"] = ("Role inventory is control-plane evidence, not an identity-token data-access test. "
                        "Conditional/custom roles, deny assignments, ABAC and network access can require separate review.")
    report["next"] = "Review exact permissions and model binding before deployment-only repair. Do not retrain or rerun setup."
    path = LAB / "reports/deployment-audit.json"
    if path.exists():
        history = LAB / "reports/inspection-history"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (history / (stamp + "-deployment.json")).write_bytes(path.read_bytes())
    path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print("\n--- SEND THIS SUMMARY ---", flush=True)
    print(json.dumps(report, indent=2, default=str), flush=True)
    print("Read-only audit complete. No roles or deployments changed. Send the summary.", flush=True)


if __name__ == "__main__":
    main()
