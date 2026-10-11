"""Explicit Lab 4 cloud steps; inspect is read-only, mutations require a named action."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config


def write(name: str, body: dict):
    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/{name}.json").write_text(json.dumps(body, indent=2, default=str),
                                          encoding="utf-8")
    print(json.dumps(body, indent=2, default=str))


def require(*names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Set configuration: " + ", ".join(missing))


def ownership(resource, cfg):
    if any((resource.tags or {}).get(key) != value for key, value in cfg.tags(4).items()):
        raise RuntimeError("resource ownership tags do not match Lab 4; no mutation performed")


def pipeline(client, cfg, code_path: str):
    from azure.ai.ml import command, dsl
    from azure.ai.ml.entities import Environment, ManagedIdentityConfiguration

    require("MONITOR_IMAGE_URI", "LOG_ANALYTICS_WORKSPACE_ID", "VAULT_URL")
    if "@sha256:" not in os.environ["MONITOR_IMAGE_URI"]:
        raise ValueError("MONITOR_IMAGE_URI must be digest-pinned")
    env = Environment(name="lab4-monitor", image=os.environ["MONITOR_IMAGE_URI"])
    variables = {name: os.environ[name] for name in
                 ("LOG_ANALYTICS_WORKSPACE_ID", "VAULT_URL")}
    variables.update(ONLINE_ENDPOINT=cfg.online_endpoint, MODEL_VERSION=cfg.model_version,
                     ALERT_SECRET_NAME=os.getenv("ALERT_SECRET_NAME", "lab4-alert-webhook"),
                     DRIFT_WINDOW_ROWS="500")
    check = command(name="lab4_drift_check", code=code_path,
                    command="python -m monitoring.job", environment=env,
                    environment_variables=variables,
                    compute=os.getenv("MONITOR_COMPUTE", "lab4monitor"),
                    identity=ManagedIdentityConfiguration())

    @dsl.pipeline(name="lab4_drift_pipeline", description="Recent production inputs vs training reference")
    def definition():
        check()

    job = definition()
    job.settings.force_rerun = True
    job.tags = cfg.tags(4)
    return job


def stage_code(destination: Path):
    # Allowlist only. Never upload cloud.env, .git, reports, credentials, or other Labs.
    for folder in ("src", "cloudlayer", "monitoring"):
        shutil.copytree(folder, destination / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "Dockerfile*"))
    (destination / "data").mkdir()
    shutil.copyfile("data/reference.csv", destination / "data/reference.csv")
    shutil.copyfile("reports/threshold-calibration.json", destination / "data/calibration.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inspect", "diagnostics", "compute", "permissions", "run", "schedule",
                                            "disable", "cleanup-plan", "cleanup"])
    parser.add_argument("--confirm-endpoint")
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--execute", action="store_true", help="apply the previewed permission grants")
    args = parser.parse_args()
    cfg = config.load()
    adapter = get_adapter(cfg)
    client = adapter._ml_client()
    compute_name = os.getenv("MONITOR_COMPUTE", "lab4monitor")
    schedule_name = os.getenv("DRIFT_SCHEDULE", "itcs355-6688012-lab4-drift")
    from azure.core.exceptions import ResourceNotFoundError

    if args.action == "inspect":
        workspace = client.workspaces.get(cfg.azureml_workspace)
        models = client.models.get(cfg.model_registry_name, cfg.model_version)
        computes = [{"name": item.name, "type": item.type, "size": getattr(item, "size", None)}
                    for item in client.compute.list()]
        write("cloud-inspection", {"checked_at": datetime.now(UTC).isoformat(),
              "workspace": workspace.name, "model": models.name, "model_version": models.version,
              "model_tags": models.tags, "compute": computes,
              "endpoint_exists": adapter.endpoint_exists(cfg.online_endpoint),
              "key_vault_resource_id": workspace.key_vault})
    elif args.action == "diagnostics":
        require("LOG_ANALYTICS_RESOURCE_ID")
        endpoint = client.online_endpoints.get(cfg.online_endpoint)
        ownership(endpoint, cfg)
        logs = [{"category": name, "enabled": True} for name in
                ("AmlOnlineEndpointConsoleLog", "AmlOnlineEndpointTrafficLog", "AmlOnlineEndpointEventLog")]
        subprocess.run(["az", "monitor", "diagnostic-settings", "create", "--name", "lab4-logs",
                        "--resource", endpoint.id, "--workspace", os.environ["LOG_ANALYTICS_RESOURCE_ID"],
                        "--export-to-resource-specific", "true", "--logs", json.dumps(logs),
                        "--output", "none"], check=True)
        write("diagnostics", {"endpoint": endpoint.name, "categories": logs,
                              "configured_at": datetime.now(UTC).isoformat()})
    elif args.action == "compute":
        from azure.ai.ml.entities import AmlCompute, IdentityConfiguration

        try:
            compute = client.compute.get(compute_name)
            ownership(compute, cfg)
        except ResourceNotFoundError:
            compute = AmlCompute(name=compute_name, size=os.getenv("MONITOR_INSTANCE", "Standard_DS1_v2"),
                                  min_instances=0, max_instances=1, idle_time_before_scale_down=120,
                                  identity=IdentityConfiguration(type="SystemAssigned"), tags=cfg.tags(4))
            compute = client.compute.begin_create_or_update(compute).result()
        identity = getattr(compute, "identity", None)
        principal = getattr(identity, "principal_id", None)
        write("monitor-compute", {"name": compute.name, "principal_id": principal,
                                  "min_instances": compute.min_instances,
                                  "max_instances": compute.max_instances,
                                  "next": "grant Log Analytics Reader and Key Vault Secrets User at resource scopes"})
    elif args.action == "permissions":
        require("LOG_ANALYTICS_RESOURCE_ID", "VAULT_URL")
        compute = client.compute.get(compute_name)
        ownership(compute, cfg)
        principal = getattr(getattr(compute, "identity", None), "principal_id", None)
        if not principal:
            raise RuntimeError("compute has no system-assigned managed identity principal")
        vault_name = os.environ["VAULT_URL"].rstrip("/").split("//", 1)[1].split(".")[0]
        vault = json.loads(subprocess.check_output(["az", "keyvault", "show", "--name", vault_name,
            "--query", "{id:id,rbac:properties.enableRbacAuthorization}", "-o", "json"], text=True))
        workspace = client.workspaces.get(cfg.azureml_workspace)
        if vault["id"].lower() != workspace.key_vault.lower():
            raise ValueError("configured vault is not the existing Lab workspace vault")
        secret_name = os.getenv("ALERT_SECRET_NAME", "lab4-alert-webhook")
        secret_scope = vault["id"] + "/secrets/" + secret_name
        plan = {"principal_id": principal, "log_role": "Log Analytics Reader",
                "log_scope": os.environ["LOG_ANALYTICS_RESOURCE_ID"],
                "vault_mode": "RBAC" if vault["rbac"] else "access policy",
                "vault_permission": "Key Vault Secrets User on the named alert secret" if vault["rbac"]
                                     else "get secret values in the existing workspace vault"}
        print(json.dumps(plan, indent=2))
        if not args.execute:
            print("Preview only. Add --execute to grant these exact permissions.")
            return
        subprocess.run(["az", "role", "assignment", "create", "--assignee-object-id", principal,
                        "--assignee-principal-type", "ServicePrincipal", "--role", "Log Analytics Reader",
                        "--scope", os.environ["LOG_ANALYTICS_RESOURCE_ID"], "--output", "none"], check=True)
        if vault["rbac"]:
            subprocess.run(["az", "role", "assignment", "create", "--assignee-object-id", principal,
                            "--assignee-principal-type", "ServicePrincipal", "--role", "Key Vault Secrets User",
                            "--scope", secret_scope, "--output", "none"], check=True)
        else:
            subprocess.run(["az", "keyvault", "set-policy", "--name", vault_name,
                            "--object-id", principal, "--secret-permissions", "get", "--output", "none"],
                            check=True)
        write("monitor-permissions", plan)
    elif args.action in ("run", "schedule"):
        if not 1 <= args.hours <= 12:
            raise ValueError("schedule lifetime must be 1 to 12 hours")
        compute = client.compute.get(compute_name)
        ownership(compute, cfg)
        with tempfile.TemporaryDirectory(prefix="lab4-monitor-code-") as folder:
            stage_code(Path(folder))
            job = pipeline(client, cfg, folder)
            if args.action == "run":
                result = client.jobs.create_or_update(job, experiment_name="lab4-drift")
                write("monitor-job", {"job_name": result.name, "created_at": datetime.now(UTC).isoformat(),
                                      "studio_url": result.studio_url})
            else:
                from azure.ai.ml.entities import JobSchedule, RecurrenceTrigger

                trigger = RecurrenceTrigger(frequency="minute", interval=5,
                                             start_time=datetime.now(UTC),
                                             end_time=datetime.now(UTC) + timedelta(hours=args.hours))
                schedule = JobSchedule(name=schedule_name, trigger=trigger,
                                       create_job=job, tags=cfg.tags(4))
                result = client.schedules.begin_create_or_update(schedule).result()
                write("drift-schedule", {"name": result.name, "is_enabled": result.is_enabled,
                      "interval_minutes": 5, "expires_after_hours": args.hours,
                      "created_at": datetime.now(UTC).isoformat()})
    elif args.action == "disable":
        schedule = client.schedules.get(schedule_name)
        ownership(schedule, cfg)
        client.schedules.begin_disable(schedule_name).result()
        assert not client.schedules.get(schedule_name).is_enabled
        write("schedule-disabled", {"name": schedule_name, "is_enabled": False,
                                     "verified_at": datetime.now(UTC).isoformat()})
    elif args.action in ("cleanup-plan", "cleanup"):
        found = {}
        for kind, operations, name in (("endpoint", client.online_endpoints, cfg.online_endpoint),
                                        ("schedule", client.schedules, schedule_name),
                                        ("compute", client.compute, compute_name)):
            try:
                resource = operations.get(name)
                ownership(resource, cfg)
                found[kind] = name
            except ResourceNotFoundError:
                pass
        active = [job.name for job in client.jobs.list()
                  if (job.tags or {}).get("lab") == "4"
                  and job.status not in ("Completed", "Failed", "Canceled", "NotResponding")]
        if args.action == "cleanup-plan":
            write("cleanup-plan", {"delete": found, "active_lab4_jobs": active,
                                    "keep": "Storage, ACR, workspace, registry, earlier Labs and Key Vault"})
            return
        if args.confirm_endpoint != cfg.online_endpoint:
            raise ValueError("cleanup requires --confirm-endpoint with the exact configured endpoint")
        if "schedule" in found:
            client.schedules.begin_disable(schedule_name).result()
        if active:
            raise RuntimeError("schedule disabled; wait for active Lab 4 jobs to finish before cleanup")
        if "schedule" in found:
            client.schedules.begin_delete(schedule_name).result()
        if "endpoint" in found:
            adapter.teardown(cfg.tags(4))
        if "compute" in found:
            client.compute.begin_delete(compute_name).result()
        remaining = {}
        for kind, operations, name in (("endpoint", client.online_endpoints, cfg.online_endpoint),
                                        ("schedule", client.schedules, schedule_name),
                                        ("compute", client.compute, compute_name)):
            try:
                operations.get(name)
                remaining[kind] = name
            except ResourceNotFoundError:
                pass
        if remaining:
            raise RuntimeError("cleanup returned but resources still exist")
        write("lab4-teardown", {"deleted": found, "remaining": remaining,
                                "verified_at": datetime.now(UTC).isoformat(),
                                "portal_confirmation": "capture manually"})


if __name__ == "__main__":
    main()
