"""Managed release-node logic, running only under the CI identity on release compute."""
import argparse
import json
import tempfile
import time
from pathlib import Path

from src.pipeline_steps import decision, write


def main():
    from azure.ai.ml import MLClient
    from azure.ai.ml.entities import (Environment, IdentityConfiguration, ManagedIdentityConfiguration,
                                      ManagedOnlineDeployment, ManagedOnlineEndpoint, Model,
                                      OnlineRequestSettings)
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import ManagedIdentityCredential

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("register", "deploy"))
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--trained", type=Path)
    parser.add_argument("--registered", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(Path("runtime.json").read_text())
    client = MLClient(ManagedIdentityCredential(client_id=cfg["ci_client_id"]),
                      cfg["subscription"], cfg["group"], cfg["workspace"], enable_telemetry=False)
    tags = {"course": "itcs355", "student": "6688012", "lab": "5"}
    if args.action == "register":
        gate = json.loads((args.gate / "gate.json").read_text())
        metrics = json.loads((args.trained / "metrics.json").read_text())
        if (gate.get("passed") is not True or gate.get("deliberate_degradation")
                or not decision(float(metrics["val_pr_auc"]), gate["incumbent"], gate["floor"], gate["margin"])):
            raise RuntimeError("Refusing registration: gate is absent, degraded or failed")
        required = ("git_commit", "data_version", "mlflow_run_id", "training_job_id", "image_digest", "seed")
        if any(metrics.get(key) in (None, "") for key in required):
            raise ValueError("Model lineage incomplete; do not register")
        model = client.models.create_or_update(Model(
            name=cfg["model_name"], path=str(args.trained / "model"), type="mlflow_model",
            description="Lab 5 managed-pipeline candidate; validation gate passed",
            tags={**tags, **{key: str(metrics[key]) for key in required},
                  "metric_val": str(metrics["val_pr_auc"]), "metric_test": str(metrics["test_pr_auc"]),
                  "promotion_stage": "Staging", "estimate_commit": cfg["estimate_commit"]}))
        write(args.out / "registered.json", {"name": model.name, "version": str(model.version),
                                             "lineage": model.tags})
    else:
        registered = json.loads((args.registered / "registered.json").read_text())
        endpoint_name = cfg["endpoint"]
        # Training and serving compete for scarce regional capacity. Wait for the
        # idle training node to disappear instead of resizing/deleting that cluster.
        deadline = time.monotonic() + 600
        while list(client.compute.list_nodes(name="lab5train")):
            if time.monotonic() >= deadline:
                raise TimeoutError("Training nodes did not scale to zero; staging was not started")
            print("Waiting for lab5train to scale to zero before staging...", flush=True)
            time.sleep(15)
        # Derive the model's internal relative directory from the SDK download layout.
        # Existing Lab 2 assets download as <destination>/<name>/model/MLmodel.
        with tempfile.TemporaryDirectory() as directory:
            client.models.download(name=registered["name"], version=registered["version"], download_path=directory)
            root = Path(directory) / registered["name"]
            manifests = list(root.rglob("MLmodel"))
            if len(manifests) != 1:
                raise RuntimeError("Cannot determine the registered MLflow model layout")
            relative_model = manifests[0].parent.relative_to(root)
            model_path = str(Path("/var/azureml-app/azureml-models") / registered["name"]
                             / registered["version"] / relative_model)
        try:
            endpoint = client.online_endpoints.get(endpoint_name)
            if any((endpoint.tags or {}).get(key) != value for key, value in tags.items()):
                raise RuntimeError("Existing endpoint belongs to another lab; refusing mutation")
        except ResourceNotFoundError:
            endpoint = ManagedOnlineEndpoint(
                name=endpoint_name, auth_mode="aml_token", tags=tags,
                identity=IdentityConfiguration(type="user_assigned", user_assigned_identities=[
                    ManagedIdentityConfiguration(resource_id=cfg["serve_identity_id"])]))
            client.online_endpoints.begin_create_or_update(endpoint).result()
        environment = Environment(image=cfg["serving_image"], inference_config={
            "liveness_route": {"port": 8080, "path": "/health"},
            "readiness_route": {"port": 8080, "path": "/ready"},
            "scoring_route": {"port": 8080, "path": "/invoke"}})
        deployment = ManagedOnlineDeployment(
            name="staging", endpoint_name=endpoint_name,
            model=f"azureml:{registered['name']}:{registered['version']}",
            environment=environment, instance_type="Standard_DS2_v2", instance_count=1, tags=tags,
            environment_variables={"MODEL_PATH": model_path,
                                   "MODEL_VERSION": registered["version"], "ONLINE_ENDPOINT": endpoint_name},
            request_settings=OnlineRequestSettings(request_timeout_ms=5000,
                                                   max_concurrent_requests_per_instance=10))
        client.online_deployments.begin_create_or_update(deployment).result()
        endpoint = client.online_endpoints.get(endpoint_name)
        endpoint.traffic = {"staging": 100}
        client.online_endpoints.begin_create_or_update(endpoint).result()
        payload = {"temp_c": 80.0, "vibration_mm_s": 3.0, "pressure_kpa": 320.0,
                   "hours_since_service": 2000.0, "load_pct": 70.0, "ambient_humidity": 58.0}
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            request.write_text(json.dumps(payload))
            response = client.online_endpoints.invoke(endpoint_name=endpoint_name, request_file=str(request))
        result = json.loads(response)
        if str(result.get("model_version")) != registered["version"]:
            raise RuntimeError("Staging returned a different model version")
        probability = result.get("probability")
        if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
            raise RuntimeError("Invalid staging prediction response")
        write(args.out / "deployment.json", {"endpoint": endpoint_name, "model": registered,
                                             "response": result, "smoke_passed": True})


if __name__ == "__main__":
    main()
