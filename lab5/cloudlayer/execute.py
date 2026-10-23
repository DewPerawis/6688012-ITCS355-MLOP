"""Explicit user-run setup and managed execution of the reviewed Lab 5 pipeline."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone

from cloudlayer.pipelines import definition
from cloudlayer.readiness import LAB, REPO, cli_json, inherited_config

TAGS = {"course": "itcs355", "student": "6688012", "lab": "5"}
REPORT = LAB / "reports" / "managed-execution.json"
TERMINAL = {"Completed", "Failed", "Canceled", "NotResponding"}


def job_status(value):
    """SDKs may return a string or Enum; str(Enum) is not the wire value."""
    raw = getattr(value, "value", value)
    token = str(raw).rsplit(".", 1)[-1].replace("_", "").replace(" ", "").lower()
    names = {"completed": "Completed", "failed": "Failed", "canceled": "Canceled",
             "cancelled": "Canceled", "notresponding": "NotResponding", "running": "Running",
             "notstarted": "NotStarted", "queued": "Queued", "preparing": "Preparing"}
    return names.get(token, str(raw))


def progress(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def save(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = REPORT.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(REPORT)


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, check=check)


def commit_source():
    if git("diff", "--cached", "--name-only").stdout.strip():
        raise ValueError("Existing staged files: stop and review them before running Part 5")
    if git("diff", "--name-only", "--diff-filter=U").stdout.strip():
        raise ValueError("Resolve existing merge conflicts first")
    # Commit implementation only. Notebooks with user outputs and financial evidence
    # remain for the later reviewed submission commit; no git add . is used.
    paths = ["lab5/README.md"]
    for folder in ("cloudlayer", "scripts", "src", "tests"):
        paths.extend(path.relative_to(REPO).as_posix() for path in (LAB / folder).rglob("*.py"))
    paths = sorted(set(paths))
    git("add", "--", *paths)
    staged = git("diff", "--cached", "--name-only").stdout.decode().splitlines()
    if not set(staged) <= set(paths):
        raise ValueError("Source commit allowlist mismatch; inspect staging")
    if staged:
        progress(f"Commit {len(staged)} allowlisted source files locally; no push")
        result = git("commit", "-m", "feat: implement Lab 5 managed training and release pipeline", "--only", "--", *paths)
        print(result.stdout.decode(), flush=True)
    return git("rev-parse", "HEAD").stdout.decode().strip()


def owned(resource):
    if any((resource.tags or {}).get(key) != value for key, value in TAGS.items()):
        raise ValueError("Resource ownership mismatch; no mutation: " + resource.name)


def wait_operation(operation, label, timeout=900):
    start = time.monotonic()
    while not operation.done():
        if time.monotonic() - start > timeout:
            raise TimeoutError(label + " still pending; operation may continue in Azure. Inspect before rerunning.")
        progress(f"{label}: provisioning ({int(time.monotonic() - start)}s)")
        time.sleep(10)
    return operation.result()


def setup(client, cfg, preview, state):
    from azure.ai.ml.entities import AmlCompute, IdentityConfiguration, ManagedIdentityConfiguration
    from azure.core.exceptions import ResourceNotFoundError

    subscription, group = cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"]
    principals = {}
    for label, suffix in (("lab5-train", "train"), ("lab5-serve", "serve")):
        name = "itcs355-6688012-lab5-" + suffix
        # List first: do not turn an access error into 'not found'.
        identities = cli_json(["identity", "list", "--subscription", subscription, "--resource-group", group,
                               "--query", "[].{id:id,name:name,principalId:principalId,tags:tags}"])
        found = next((identity for identity in identities if identity["name"] == name), None)
        if found:
            if any((found.get("tags") or {}).get(k) != v for k, v in TAGS.items()):
                raise ValueError("Existing identity is not tagged for Lab 5: " + name)
        else:
            progress("Create identity: " + name)
            found = cli_json(["identity", "create", "--subscription", subscription, "--resource-group", group,
                              "--name", name, "--location", cfg["REGION"],
                              "--tags", "course=itcs355", "student=6688012", "lab=5"])
        principals[label] = found["principalId"]
        state.setdefault("identities", {})[label] = {"id": found["id"], "principal_id": found["principalId"]}
        save(state)
    ci = cli_json(["identity", "show", "--subscription", subscription, "--resource-group", group,
                   "--name", "itcs355-6688012-lab4-ci", "--query", "{principalId:principalId,clientId:clientId}"])
    if ci["clientId"] != preview["runtime"]["ci_client_id"]:
        raise ValueError("CI identity changed since the preview")
    principals["existing lab4-ci"] = ci["principalId"]
    workspace_scope = (f"/subscriptions/{subscription}/resourceGroups/{group}"
                       f"/providers/Microsoft.MachineLearningServices/workspaces/{cfg['AZUREML_WORKSPACE']}")
    workspace_roles = cli_json(["role", "assignment", "list", "--subscription", subscription,
                                "--scope", workspace_scope, "--include-inherited",
                                "--query", f"[?principalId=='{ci['principalId']}'].roleDefinitionName"])
    if not set(workspace_roles) & {"Owner", "Contributor"}:
        raise ValueError("Existing CI workspace Contributor role is missing; no broad role will be added automatically")
    registry_scope = next(item["scope"] for item in preview["role_plan"] if item["role"] == "AcrPull")
    registry_roles = cli_json(["role", "assignment", "list", "--subscription", subscription,
                               "--scope", registry_scope, "--include-inherited",
                               "--query", f"[?principalId=='{ci['principalId']}'].roleDefinitionName"])
    if not set(registry_roles) & {"AcrPull", "AcrPush"}:
        raise ValueError("Existing CI ACR pull/push role is missing; review before release compute starts")
    state["roles"] = []
    for item in preview["role_plan"]:
        principal = principals[item["identity"]]
        query = f"[?principalId=='{principal}' && roleDefinitionName=='{item['role']}'].id"
        existing = cli_json(["role", "assignment", "list", "--subscription", subscription,
                             "--scope", item["scope"], "--include-inherited", "--query", query])
        progress(("Verify" if existing else "Grant") + " " + item["role"] + " to " + item["identity"])
        if not existing:
            result = cli_json(["role", "assignment", "create", "--subscription", subscription,
                               "--assignee-object-id", principal, "--assignee-principal-type", "ServicePrincipal",
                               "--role", item["role"], "--scope", item["scope"], "--query", "{id:id}"])
            existing = [result["id"]]
        state["roles"].append({**item, "assignment_ids": existing})
        save(state)
    for item in preview["proposed_compute"]:
        name = item["name"]
        identity_id = preview["runtime"]["train_identity_id"] if name == "lab5train" else preview["runtime"]["ci_identity_id"]
        try:
            compute = client.compute.get(name)
            owned(compute)
        except ResourceNotFoundError:
            progress("Create min=0/max=1 compute: " + name)
            compute = wait_operation(client.compute.begin_create_or_update(AmlCompute(
                name=name, size=item["sku"], tier="dedicated", min_instances=0, max_instances=1,
                idle_time_before_scale_down=120, ssh_public_access_enabled=False, tags=TAGS,
                identity=IdentityConfiguration(type="user_assigned", user_assigned_identities=[
                    ManagedIdentityConfiguration(resource_id=identity_id)]))), "Compute " + name)
        attached = [identity.resource_id.lower() for identity in (compute.identity.user_assigned_identities or [])]
        if (compute.size.lower() != item["sku"].lower() or compute.min_instances != 0
                or compute.max_instances != 1 or compute.idle_time_before_scale_down != 120
                or str(compute.tier).lower() != "dedicated" or attached != [identity_id.lower()]):
            raise ValueError("Existing compute shape/identity differs from reviewed plan: " + name)
        state.setdefault("compute", {})[name] = {"size": compute.size, "min": 0, "max": 1,
                                                  "identity_id": identity_id}
        save(state)


def endpoint_exists(client, name):
    from azure.core.exceptions import ResourceNotFoundError

    try:
        client.online_endpoints.get(name)
        return True
    except ResourceNotFoundError:
        return False


def wait_job(client, name, state, record):
    started = time.monotonic()
    while True:
        job = client.jobs.get(name)
        record["status"] = job_status(job.status)
        record["status_raw"] = str(job.status)
        record["studio_url"] = job.studio_url
        save(state)
        progress("Job " + name + ": " + record["status"])
        if record["status"] in TERMINAL:
            children = list(client.jobs.list(parent_job_name=name))
            record["steps"] = [{"name": child.name, "display_name": child.display_name,
                                "status": job_status(child.status)} for child in children]
            save(state)
            return job
        if time.monotonic() - started > 2700:
            raise TimeoutError("Managed job still running after 45 minutes. It is NOT canceled; inspect Studio before rerunning.")
        time.sleep(15)


def run_variant(client, preview, state, degraded, *, label=None, document=None):
    import yaml
    from azure.ai.ml import load_job
    from azure.core.exceptions import ResourceNotFoundError

    label = label or ("degraded" if degraded else "normal")
    record = state.setdefault("jobs", {}).setdefault(label, {"name": state["run_prefix"] + "-" + label})
    save(state)  # Persist the deterministic job name before submission to avoid duplicate jobs on retry.
    try:
        job = client.jobs.get(record["name"])
        progress("Resume observation of existing job: " + record["name"])
    except ResourceNotFoundError:
        code = REPO / state["bundle"]
        if document is None:
            document = definition(state["runtime"], str(code), preview["raw_sha256"], degraded)
        path = REPORT.parent / (record["name"] + ".yaml")
        path.write_text(yaml.safe_dump(document, sort_keys=False))
        job = load_job(source=path)
        job.name = record["name"]
        job.tags.update(estimate_commit=preview["estimate_commit"], git_commit=state["source_commit"])
        record["source_commit"] = state["source_commit"]
        progress("Submit managed pipeline: " + record["name"])
        client.jobs.create_or_update(job)
        record["submitted_at"] = datetime.now(timezone.utc).isoformat()
        save(state)
    job = wait_job(client, record["name"], state, record)
    versions = sorted(str(model.version) for model in client.models.list(name=state["runtime"]["model_name"]))
    if degraded:
        failed_gate = any(step["display_name"] == "evaluate" and step["status"] == "Failed"
                          for step in record["steps"])
        downstream_ran = any(step["display_name"] in ("register", "deploy_staging")
                             and step["status"] in ("Completed", "Running") for step in record["steps"])
        record["no_registration"] = versions == state["baseline_model_versions"]
        record["no_endpoint"] = not endpoint_exists(client, state["runtime"]["endpoint"])
        record["expected_gate_failure_verified"] = (job_status(job.status) == "Failed" and failed_gate
                                                     and not downstream_ran and record["no_registration"]
                                                     and record["no_endpoint"])
        save(state)
        if not record["expected_gate_failure_verified"]:
            raise RuntimeError("Negative pipeline failed for an unexpected reason or changed registry/endpoint; inspect child steps")
    else:
        if job_status(job.status) != "Completed":
            raise RuntimeError("Normal managed pipeline did not complete; inspect the child job log in Studio")
        if not endpoint_exists(client, state["runtime"]["endpoint"]):
            raise RuntimeError("Pipeline completed without its staging endpoint")
        record["new_model_versions"] = sorted(set(versions) - set(state["baseline_model_versions"]))
        fields = ("git_commit", "data_version", "mlflow_run_id", "training_job_id", "image_digest",
                  "seed", "metric_val", "metric_test", "promotion_stage", "estimate_commit")
        record["registered_models"] = []
        for version in record["new_model_versions"]:
            model = client.models.get(state["runtime"]["model_name"], version)
            record["registered_models"].append({"name": model.name, "version": str(model.version),
                                                "lineage": {key: value for key, value in (model.tags or {}).items()
                                                            if key in fields}})
        record["endpoint"] = state["runtime"]["endpoint"]
        save(state)


def main():
    import yaml
    from azure.ai.ml import MLClient, load_job
    from azure.identity import AzureCliCredential

    preview = json.loads((LAB / "reports/pipeline-preview.json").read_text())
    if preview.get("status") != "preview_ready":
        raise ValueError("A successful Part 4 preview is required")
    cfg, _ = inherited_config()
    for key, runtime_key in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                             ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != preview["runtime"][runtime_key].lower():
            raise ValueError("Configuration differs from reviewed Part 4 scopes: " + key)
    group_prefix = (f"/subscriptions/{cfg['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{cfg['AZURE_RESOURCE_GROUP']}/").lower()
    allowed_roles = {"Storage Blob Data Contributor", "Storage Blob Data Reader", "AcrPull", "Managed Identity Operator"}
    if len(preview["role_plan"]) != 8 or any(
        item["role"] not in allowed_roles or not item["scope"].lower().startswith(group_prefix)
        for item in preview["role_plan"]
    ):
        raise ValueError("Role plan differs from the reviewed scoped assignments")
    state = json.loads(REPORT.read_text()) if REPORT.exists() else {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "run_prefix": "lab5-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "estimate_commit": preview["estimate_commit"], "status": "preparing"}
    try:
        progress("1/5 Verify estimate, budget assumptions and commit implementation source")
        estimate = json.loads((LAB / "reports/estimate-commit.json").read_text())
        blob = git("show", estimate["estimate_commit"] + ":" + estimate["estimate_path"]).stdout
        if hashlib.sha256(blob).hexdigest() != estimate["estimate_sha256"]:
            raise ValueError("Estimate commit verification failed")
        # A conservative planning conversion/reserve, never claimed as measured FX or full-term billing.
        billing = json.loads((LAB / "reports/billing-review.json").read_text())
        for observed in (preview["prepared_at"], billing["group_billing"]["queried_at"]):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(observed)).total_seconds()
            if not 0 <= age <= 86400:
                raise ValueError("Preview/billing observation is over 24h old; refresh read-only evidence first")
        totals = billing["group_billing"]["posted_totals_by_currency"]
        if set(totals) != {"USD"}:
            raise ValueError("Review billing currencies before using this planning envelope")
        planned = totals["USD"] * 40 + 44.8282 + 200
        if planned >= 800:
            raise ValueError("Conservative planning envelope exceeds 800 THB; do not start compute")
        state["budget_planning"] = {"posted_usd": totals["USD"], "assumed_thb_per_usd": 40,
                                    "unposted_other_scope_reserve_thb": 200, "lab5_envelope_thb": 44.8282,
                                    "combined_planning_envelope_thb": round(planned, 4),
                                    "full_term_actual_verified": False,
                                    "note": "Explicit planning assumptions, not measured FX or proof of full-term cost compliance."}
        if not state.get("source_commit"):
            state["source_commit"] = commit_source()
            save(state)
        else:
            # A controller-only status fix must not force retraining an unchanged
            # frozen runtime bundle. Still reject edits to any code that runs remotely
            # or changes the compiled DAG.
            core = ["lab5/" + relative for relative in state["bundle_hashes"] if relative != "runtime.json"]
            core.append("lab5/cloudlayer/pipelines.py")
            if git("diff", state["source_commit"], "--", *core).stdout.strip():
                raise ValueError("Source changed after this execution began. Inspect prior jobs before starting a revised execution")
        if not state.get("bundle"):
            destination = LAB / "_bundles" / state["run_prefix"]
            for relative in preview["bundle_hashes"]:
                if relative == "runtime.json":
                    continue
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(LAB / relative, target)
            state["runtime"] = {**preview["runtime"], "source_base_commit": state["source_commit"]}
            (destination / "runtime.json").write_text(json.dumps(state["runtime"], indent=2))
            state["bundle"] = destination.relative_to(REPO).as_posix()
            state["bundle_hashes"] = {path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in destination.rglob("*") if path.is_file()}
            save(state)
        client = MLClient(AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
                          cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
                          enable_telemetry=False)
        # Parse both current definitions before any Azure mutation, including changes
        # made since the successful Part 4 parse. This never submits a job.
        for degraded in (True, False):
            label = "degraded" if degraded else "normal"
            path = REPORT.parent / (state["run_prefix"] + "-" + label + ".yaml")
            path.write_text(yaml.safe_dump(definition(state["runtime"], str(REPO / state["bundle"]),
                                                       preview["raw_sha256"], degraded), sort_keys=False))
            load_job(source=path)
        progress("2/5 Create/verify the reviewed identities, eight scoped roles and min=0 compute")
        setup(client, cfg, preview, state)
        if "baseline_model_versions" not in state:
            if endpoint_exists(client, state["runtime"]["endpoint"]):
                raise ValueError("Lab 5 endpoint already exists before negative-control run; inspect before continuing")
            state["baseline_model_versions"] = sorted(str(model.version) for model in client.models.list(name=cfg["MODEL_REGISTRY_NAME"]))
            save(state)
        progress("3/5 Run the genuinely degraded candidate; verify no registration/deployment")
        if not state.get("jobs", {}).get("degraded", {}).get("expected_gate_failure_verified"):
            run_variant(client, preview, state, degraded=True)
        progress("4/5 Run the normal candidate through gate, registry, staging and smoke test")
        run_variant(client, preview, state, degraded=False)
        progress("5/5 Save actual managed-run evidence; staging remains running for the next exercise")
        state["status"] = "managed_pipeline_completed"
        state["cleanup_pending"] = True
        save(state)
    except Exception as exc:
        state["status"] = "needs_attention"
        state["error_type"] = type(exc).__name__
        state["error_message"] = str(exc)[:1000]
        state["cleanup_pending"] = bool(state.get("compute") or state.get("jobs") or state.get("identities"))
        save(state)
        print("Managed execution stopped. Existing operations/resources may remain; do not submit duplicate jobs.", flush=True)
        raise
    finally:
        summary = {key: state[key] for key in ("status", "source_commit", "estimate_commit", "budget_planning",
                                              "jobs", "cleanup_pending", "error_type", "error_message") if key in state}
        print("\n--- SEND THIS SUMMARY ---", flush=True)
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
