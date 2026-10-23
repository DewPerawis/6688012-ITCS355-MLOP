"""Part 4: local contract/gate rehearsal, read-only cloud checks and resource preview."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone

from cloudlayer.pipelines import definition
from cloudlayer.readiness import LAB, REPO, cli_json, inherited_config, retail_prices
from scripts.plan_run import select_linux_meter
from scripts.preflight import progress
from src import data
from src.pipeline_steps import contract, decision


def main():
    import yaml
    from azure.ai.ml import MLClient, load_job
    from azure.identity import AzureCliCredential

    progress("1/4 Verify committed estimate and previous observations")
    cfg, _ = inherited_config()
    report_dir = LAB / "reports"
    estimate = json.loads((report_dir / "estimate-commit.json").read_text())
    blob = subprocess.run(["git", "show", estimate["estimate_commit"] + ":" + estimate["estimate_path"]],
                          cwd=REPO, capture_output=True, check=True).stdout
    if hashlib.sha256(blob).hexdigest() != estimate["estimate_sha256"]:
        raise ValueError("Committed estimate hash mismatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", estimate["estimate_commit"], "HEAD"],
                   cwd=REPO, check=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    billing = json.loads((report_dir / "billing-review.json").read_text())
    if billing.get("group_billing", {}).get("status") != "ok":
        raise ValueError("A posted billing observation is required before resource planning")
    source = REPO / "lab2/data/raw/sensors.csv"
    raw_sha = hashlib.sha256(source.read_bytes()).hexdigest()

    progress("2/4 Rehearse the real data contract plus synthetic pass/fail gate probes")
    frame = data.load_raw(source)
    parts = contract(frame)
    bad = frame.drop(columns=[data.FEATURES[0]])
    try:
        contract(bad)
    except ValueError:
        contract_blocked = True
    else:
        raise ValueError("Broken contract unexpectedly passed")
    preflight = json.loads((report_dir / "preflight.json").read_text())
    incumbent = float(preflight["incumbent"]["lineage"]["metric_val"])
    probes = {"pass": decision(incumbent + 0.01, incumbent),
              "degraded_blocked": not decision(0.0, incumbent),
              "unchanged_blocked": not decision(incumbent, incumbent)}
    if not all(probes.values()):
        raise ValueError("Local gate probes failed")

    progress("3/4 Read datastores, CI identity, ACR images and workspace tracking URI")
    client = MLClient(AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
                      cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
                      enable_telemetry=False)
    store = client.datastores.get("itcs355blob")
    default_store = client.datastores.get_default()
    raw_object = cli_json(["storage", "blob", "show", "--auth-mode", "login",
                           "--account-name", store.account_name, "--container-name", store.container_name,
                           "--name", "itcs355/lab2/data/sensors.csv",
                           "--query", "{size:properties.contentLength}"])
    if raw_object.get("size") != source.stat().st_size:
        raise ValueError("Cloud Lab 2 input is missing or has a different size; do not submit")
    workspace = client.workspaces.get(cfg["AZUREML_WORKSPACE"])
    live_model = client.models.get(cfg["MODEL_REGISTRY_NAME"], cfg["MODEL_VERSION"])
    if float(live_model.tags["metric_val"]) != incumbent:
        raise ValueError("Incumbent metadata changed; review the gate policy")
    identity = cli_json(["identity", "show", "--subscription", cfg["AZURE_SUBSCRIPTION_ID"],
                         "--resource-group", cfg["AZURE_RESOURCE_GROUP"],
                         "--name", "itcs355-6688012-lab4-ci",
                         "--query", "{id:id,clientId:clientId,principalId:principalId}"])
    login, repository = cfg["CONTAINER_REGISTRY"].split("/", 1)
    registries = cli_json(["acr", "list", "--subscription", cfg["AZURE_SUBSCRIPTION_ID"],
                          "--resource-group", cfg["AZURE_RESOURCE_GROUP"],
                          "--query", "[].{id:id,name:name,loginServer:loginServer}"])
    registry = next(item for item in registries if item["loginServer"] == login)
    train_digest = live_model.tags["image_digest"]
    serving = json.loads((REPO / "lab4/reports/image-push.json").read_text())["digest"]
    training = cfg["CONTAINER_REGISTRY"] + "@" + train_digest
    for image in (training, serving):
        reference = image.partition("/")[2]
        found = cli_json(["acr", "repository", "show", "--name", registry["name"],
                          "--subscription", cfg["AZURE_SUBSCRIPTION_ID"], "--image", reference,
                          "--query", "{digest:digest}"])
        if found.get("digest") != image.partition("@")[2]:
            raise ValueError("Pinned image is unavailable or has a different digest")
    scope = f"/subscriptions/{cfg['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{cfg['AZURE_RESOURCE_GROUP']}"
    train_identity = scope + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/itcs355-6688012-lab5-train"
    serve_identity = scope + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/itcs355-6688012-lab5-serve"
    raw_uri = "azureml://datastores/itcs355blob/paths/itcs355/lab2/data/sensors.csv"
    runtime = {"subscription": cfg["AZURE_SUBSCRIPTION_ID"], "group": cfg["AZURE_RESOURCE_GROUP"],
               "workspace": cfg["AZUREML_WORKSPACE"], "model_name": cfg["MODEL_REGISTRY_NAME"],
               "incumbent_version": cfg["MODEL_VERSION"], "incumbent_metric": incumbent,
               "train_identity_id": train_identity, "serve_identity_id": serve_identity,
               "ci_identity_id": identity["id"], "ci_client_id": identity["clientId"],
               "training_image": training, "serving_image": serving,
               "endpoint": "itcs355-6688012-lab5", "raw_uri": raw_uri,
               "data_version": live_model.tags["data_version"], "source_base_commit": base,
               "estimate_commit": estimate["estimate_commit"], "tracking_uri": workspace.mlflow_tracking_uri}
    release_prices = retail_prices(workspace.location, sku="Standard_DS1_v2")
    release_meter = select_linux_meter(release_prices, sku="Standard_DS1_v2")
    if release_meter["retailPrice"] > select_linux_meter(preflight["prices"])["retailPrice"]:
        raise ValueError("Release SKU exceeds the existing conservative compute rate; revise the estimate")

    def container_scope(datastore):
        return (scope + "/providers/Microsoft.Storage/storageAccounts/" + datastore.account_name
                + "/blobServices/default/containers/" + datastore.container_name)

    training_storage, default_storage = container_scope(store), container_scope(default_store)
    roles = [
        {"identity": "lab5-train", "role": "Storage Blob Data Contributor", "scope": training_storage},
        {"identity": "lab5-train", "role": "Storage Blob Data Reader", "scope": default_storage},
        {"identity": "lab5-train", "role": "AcrPull", "scope": registry["id"]},
        {"identity": "existing lab4-ci", "role": "Storage Blob Data Contributor", "scope": training_storage},
        {"identity": "existing lab4-ci", "role": "Storage Blob Data Contributor", "scope": default_storage},
        {"identity": "existing lab4-ci", "role": "Managed Identity Operator", "scope": serve_identity},
        {"identity": "lab5-serve", "role": "Storage Blob Data Reader", "scope": default_storage},
        {"identity": "lab5-serve", "role": "AcrPull", "scope": registry["id"]},
    ]
    progress("4/4 Stage source allowlist, compile/parse six-step pipeline and write permission preview")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    bundle = LAB / "_bundles" / stamp
    bundle.mkdir(parents=True)
    for relative in ("src/__init__.py", "src/data.py", "src/pipeline_steps.py",
                     "cloudlayer/__init__.py", "cloudlayer/release.py", "cloudlayer/run_step.py"):
        destination = bundle / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(LAB / relative, destination)
    (bundle / "runtime.json").write_text(json.dumps(runtime, indent=2))
    bundle_hashes = {str(path.relative_to(bundle)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in bundle.rglob("*") if path.is_file()}
    paths = []
    for variant, degraded in (("pipeline", False), ("pipeline-degraded", True)):
        path = report_dir / f"{variant}-{stamp}.yaml"
        code_relative_to_report = "../" + str(bundle.relative_to(LAB)).replace("\\", "/")
        path.write_text(yaml.safe_dump(definition(runtime, code_relative_to_report, raw_sha, degraded), sort_keys=False))
        load_job(source=path)  # Local schema parsing only: does not submit or validate cloud capacity.
        paths.append(str(path.relative_to(LAB)))
    result = {"prepared_at": datetime.now(timezone.utc).isoformat(), "status": "preview_ready",
              "estimate_commit": estimate["estimate_commit"], "source_base_commit": base,
              "local_rehearsal": {"split_rows": [len(part) for part in parts],
                                  "broken_contract_blocked": contract_blocked, "synthetic_gate_probes": probes},
              "gate_policy": {"metric": "val_pr_auc", "floor": 0.40, "minimum_delta": 0.002,
                              "incumbent": incumbent, "seed": 20260101,
                              "limitation": "Single-seed operational guard; not statistical evidence of a stable gain."},
              "source_bundle": str(bundle.relative_to(LAB)), "bundle_hashes": bundle_hashes,
              "pipeline_files": paths, "raw_sha256": raw_sha, "runtime": runtime,
              "release_price_reference": release_prices,
              "proposed_compute": [{"name": "lab5train", "sku": "Standard_DS2_v2", "identity": "lab5-train"},
                                   {"name": "lab5release", "sku": "Standard_DS1_v2", "identity": "existing lab4-ci"}],
              "compute_limits": {"min": 0, "max_per_cluster": 1, "idle_scale_down_seconds": 120},
              "identity_selection": {"training": "Compute must attach only the Lab 5 training UAI; job uses type=managed",
                                     "release": "CI selected explicitly by client_id on separate release compute"},
              "new_identities": [train_identity, serve_identity], "role_plan": roles,
              "existing_ci_workspace_roles": "Must verify existing workspace Contributor and ACR pull access before submission",
              "discounted_compute": "unmet: observed TotalLowPriorityCores=0; dedicated fallback proposed",
              "budget": {"posted_usd": billing["group_billing"]["posted_totals_by_currency"].get("USD"),
                         "term_thb_verified": False},
              "cloud_mutations": False, "managed_jobs_submitted": False,
              "next": "Review resource/role plan, source commit and budget before any execution. No managed result claimed."}
    output = report_dir / "pipeline-preview.json"
    if output.exists():
        history = report_dir / "pipeline-preview-history"
        history.mkdir(exist_ok=True)
        shutil.copyfile(output, history / (stamp + ".json"))
    output.write_text(json.dumps(result, indent=2) + "\n")
    summary = {key: result[key] for key in ("status", "estimate_commit", "local_rehearsal", "gate_policy",
                                          "proposed_compute", "discounted_compute", "budget", "cloud_mutations",
                                          "managed_jobs_submitted")}
    summary["planned_role_assignments"] = len(roles)
    summary["images"] = "Both historical digest-pinned images were found in ACR"
    summary["report"] = "lab5/reports/pipeline-preview.json"
    print("\n--- SEND THIS SUMMARY ---", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    print(result["next"], flush=True)


if __name__ == "__main__":
    main()
