"""User-run cleanup of the three named Lab 5 runtime resources; retain model evidence."""
import json
from datetime import datetime, timezone

from cloudlayer.execute import REPORT, TAGS, TERMINAL, job_status, owned, progress, wait_operation
from cloudlayer.readiness import LAB, inherited_config


def main():
    from azure.ai.ml import MLClient
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import AzureCliCredential

    state = json.loads(REPORT.read_text())
    cfg, _ = inherited_config()
    runtime = state["runtime"]
    for key, field in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                       ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != runtime[field].lower():
            raise ValueError("Workspace differs from the recorded run")
    if state.get("jobs", {}).get("deploy-repair-v2", {}).get("smoke_passed") is not True:
        raise ValueError("Successful model-v3 smoke evidence is required before cleanup")
    client = MLClient(AzureCliCredential(subscription=runtime["subscription"]), runtime["subscription"],
                      runtime["group"], runtime["workspace"], enable_telemetry=False)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "checking",
              "scope": "named endpoint and two tagged Lab 5 compute clusters only",
              "removed": [], "absent_after": [], "retained": ["model versions including v3", "job history",
              "Storage", "ACR", "workspace", "identities and role evidence"],
              "portal_empty_screenshot": "pending manual confirmation",
              "billing_24h": "pending; absence of runtime resources does not prove zero future charges"}
    path = LAB / "reports/cleanup-runtime.json"
    if path.exists():
        history = LAB / "reports/inspection-history"
        history.mkdir(exist_ok=True)
        (history / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-cleanup.json")).write_bytes(path.read_bytes())
    try:
        progress("1/3 Read jobs, schedules and ownership before deleting any resources")
        # Include tagged jobs beyond the locally recorded names; do not cancel running work.
        for job in client.jobs.list():
            if all((job.tags or {}).get(k) == v for k, v in TAGS.items()):
                if job_status(job.status) not in TERMINAL:
                    raise ValueError("A Lab 5 job is active; cleanup stopped: " + job.name)
        schedules = [schedule for schedule in client.schedules.list()
                     if all((schedule.tags or {}).get(k) == v for k, v in TAGS.items())]
        report["tagged_schedules"] = [item.name for item in schedules]
        if schedules:
            raise ValueError("Lab 5 schedules exist; review them before deleting runtime resources")
        resources = []
        for label, operations, name in (("endpoint", client.online_endpoints, runtime["endpoint"]),
                                         ("compute", client.compute, "lab5train"),
                                         ("compute", client.compute, "lab5release")):
            try:
                resource = operations.get(name)
                owned(resource)
                resources.append((label, operations, name))
            except ResourceNotFoundError:
                report["absent_after"].append(label + ":" + name)
        # All scope/ownership checks pass before the first deletion.
        progress("2/3 Delete only: " + ", ".join(label + ":" + name for label, _, name in resources))
        for label, operations, name in resources:
            wait_operation(operations.begin_delete(name=name), "Delete " + label + ":" + name)
            report["removed"].append(label + ":" + name)
            path.write_text(json.dumps(report, indent=2) + "\n")
        progress("3/3 Recheck resource absence and retained registered model v3")
        for label, operations, name in resources:
            try:
                operations.get(name)
            except ResourceNotFoundError:
                report["absent_after"].append(label + ":" + name)
            else:
                raise RuntimeError("Resource still present after deletion: " + name)
        model = client.models.get(runtime["model_name"], "3")
        report["retained_model"] = {"name": model.name, "version": str(model.version)}
        report["status"] = "named_runtime_removed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        # Do not rewrite model/run lineage or mark full Lab 5 completed.
        state["cleanup_pending"] = False
        state["cleanup_runtime_report"] = "lab5/reports/cleanup-runtime.json"
        REPORT.write_text(json.dumps(state, indent=2) + "\n")
    except Exception as exc:
        report.update(status="needs_attention", error_type=type(exc).__name__, error=str(exc)[:1500])
        raise
    finally:
        path.write_text(json.dumps(report, indent=2) + "\n")
        print("\n--- SEND THIS SUMMARY ---", flush=True)
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
