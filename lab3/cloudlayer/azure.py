"""Azure ML managed-online-endpoint implementation for Lab 3."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential

from cloudlayer.base import CloudAdapter

ACR_SUFFIX = ".azurecr.io"
RESOURCE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")


def _run_output(args: list[str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _model_ref(value: str) -> tuple[str, str]:
    name, separator, version = value.rpartition(":")
    if not separator or not name or not version.isdigit():
        raise ValueError("model_ref must be an exact name:integer-version reference")
    return name, version


def _model_mount_path(name: str, version: str, artifact_subdir: str = "model") -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not version.isdigit():
        raise ValueError("unsafe model name or version")
    if artifact_subdir and not re.fullmatch(r"[A-Za-z0-9_.-]+", artifact_subdir):
        raise ValueError("unsafe model artifact subdirectory")
    root = f"/var/azureml-app/azureml-models/{name}/{version}"
    return f"{root}/{artifact_subdir}" if artifact_subdir else root


def _validate_traffic(allocations: dict[str, int]) -> dict[str, int]:
    if not allocations or sum(allocations.values()) != 100:
        raise ValueError("traffic percentages must be non-empty and total exactly 100")
    if any(not RESOURCE_NAME.fullmatch(name) for name in allocations):
        raise ValueError("invalid deployment name in traffic allocation")
    if any(value < 0 or value > 100 for value in allocations.values()):
        raise ValueError("traffic percentages must be between 0 and 100")
    return dict(allocations)


class AzureAdapter(CloudAdapter):
    def _ml_client(self):
        if not self.cfg.azure_subscription_id:
            raise RuntimeError("AZURE_SUBSCRIPTION_ID is required")
        from azure.ai.ml import MLClient

        return MLClient(
            DefaultAzureCredential(),
            self.cfg.azure_subscription_id,
            self.cfg.azure_resource_group,
            self.cfg.azureml_workspace,
        )

    def tracking_uri(self) -> str:
        workspace = self._ml_client().workspaces.get(self.cfg.azureml_workspace)
        if not workspace.mlflow_tracking_uri:
            raise RuntimeError("workspace returned no MLflow tracking URI")
        return workspace.mlflow_tracking_uri

    def download_model(self, name: str, version: str, destination: str) -> str:
        """Download a workspace model asset without requiring the MLflow Azure plugin."""
        if not version.isdigit():
            raise ValueError("model version must be an integer string")
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        client = self._ml_client()
        model = client.models.get(name=name, version=version)
        if str(model.version) != version:
            raise RuntimeError(f"requested model version {version}, got {model.version}")
        client.models.download(name=name, version=version, download_path=str(target))
        model_files = list(target.rglob("MLmodel"))
        if len(model_files) != 1:
            raise RuntimeError(
                f"expected one MLmodel below {target}, found {len(model_files)}"
            )
        return str(model_files[0].parent.resolve())

    def push_image(self, local_tag: str) -> str:
        registry = self.cfg.container_registry.strip().rstrip("/")
        if "/" not in registry:
            raise ValueError("CONTAINER_REGISTRY must be login-server/repository")
        login_server, repository = registry.split("/", 1)
        if not login_server.endswith(ACR_SUFFIX) or not repository:
            raise ValueError("CONTAINER_REGISTRY must identify an Azure registry repository")
        local_name = local_tag.rsplit("/", 1)[-1]
        tag = local_name.rsplit(":", 1)[1] if ":" in local_name else "latest"
        remote_tag = f"{login_server}/{repository}-serve:{tag}"
        query = f"[?loginServer=='{login_server}'].name | [0]"
        registry_name = _run_output(["az", "acr", "list", "--query", query, "-o", "tsv"])
        if not registry_name:
            raise RuntimeError(f"no accessible ACR matches {login_server}")
        subprocess.run(["az", "acr", "login", "--name", registry_name], check=True)
        docker = os.environ.get("DOCKER", "docker")
        subprocess.run([docker, "tag", local_tag, remote_tag], check=True)
        subprocess.run([docker, "push", remote_tag], check=True)
        digest = _run_output(
            [
                "az",
                "acr",
                "repository",
                "show",
                "--name",
                registry_name,
                "--image",
                f"{repository}-serve:{tag}",
                "--query",
                "digest",
                "-o",
                "tsv",
            ]
        )
        if not digest.startswith("sha256:"):
            raise RuntimeError("ACR did not return a valid digest")
        return f"{login_server}/{repository}-serve@{digest}"

    def deploy(self, model_ref: str, endpoint: str, instance: str) -> str:
        if not self.cfg.serving_image_uri or "@sha256:" not in self.cfg.serving_image_uri:
            raise ValueError("SERVING_IMAGE_URI must be digest-pinned")
        if not RESOURCE_NAME.fullmatch(endpoint):
            raise ValueError("ONLINE_ENDPOINT must be 3-32 lowercase letters, digits, or hyphens")
        deployment_name = self.cfg.deployment_name
        if not RESOURCE_NAME.fullmatch(deployment_name):
            raise ValueError("DEPLOYMENT_NAME is invalid")
        model_name, version = _model_ref(model_ref)

        from azure.ai.ml.entities import (
            Environment,
            ManagedOnlineDeployment,
            ManagedOnlineEndpoint,
            OnlineRequestSettings,
        )
        from azure.core.exceptions import ResourceNotFoundError

        client = self._ml_client()
        try:
            online_endpoint = client.online_endpoints.get(endpoint)
            endpoint_tags = online_endpoint.tags or {}
            if any(endpoint_tags.get(k) != v for k, v in self.cfg.tags(3).items()):
                raise RuntimeError("existing endpoint tags do not match this Lab 3")
        except ResourceNotFoundError:
            online_endpoint = ManagedOnlineEndpoint(
                name=endpoint,
                auth_mode="key",
                description="ITCS355 Lab 3 serving endpoint",
                tags=self.cfg.tags(3),
            )
            client.online_endpoints.begin_create_or_update(online_endpoint).result()

        environment = Environment(
            image=self.cfg.serving_image_uri,
            inference_config={
                "liveness_route": {"port": 8080, "path": "/health"},
                "readiness_route": {"port": 8080, "path": "/ready"},
                "scoring_route": {"port": 8080, "path": "/invoke"},
            },
        )
        deployment = ManagedOnlineDeployment(
            name=deployment_name,
            endpoint_name=endpoint,
            model=f"azureml:{model_name}:{version}",
            environment=environment,
            environment_variables={
                "MODEL_PATH": _model_mount_path(model_name, version),
                "MODEL_VERSION": version,
            },
            instance_type=instance,
            instance_count=1,
            request_settings=OnlineRequestSettings(
                request_timeout_ms=5000,
                max_concurrent_requests_per_instance=self.cfg.target_concurrency,
            ),
            tags={**self.cfg.tags(3), "model_version": version},
        )
        client.online_deployments.begin_create_or_update(deployment).result()

        endpoint_state = client.online_endpoints.get(endpoint)
        traffic = dict(endpoint_state.traffic or {})
        if not traffic or sum(traffic.values()) == 0:
            endpoint_state.traffic = {deployment_name: 100}
            client.online_endpoints.begin_create_or_update(endpoint_state).result()
        return str(client.online_endpoints.get(endpoint).scoring_uri)

    def invoke(
        self,
        endpoint: str,
        payload: dict[str, Any],
        deployment: str | None = None,
    ) -> dict[str, Any]:
        request_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", encoding="utf-8", delete=False
            ) as request_file:
                json.dump(payload, request_file)
                request_path = Path(request_file.name)
            result = self._ml_client().online_endpoints.invoke(
                endpoint_name=endpoint,
                deployment_name=deployment,
                request_file=str(request_path),
            )
            parsed = json.loads(result) if isinstance(result, str) else result
            if not isinstance(parsed, dict):
                raise TypeError("endpoint response must be a JSON object")
            return parsed
        finally:
            if request_path is not None:
                request_path.unlink(missing_ok=True)

    def set_traffic(self, endpoint: str, allocations: dict[str, int]) -> dict[str, int]:
        requested = _validate_traffic(allocations)
        client = self._ml_client()
        existing = {
            item.name
            for item in client.online_deployments.list(endpoint_name=endpoint)
        }
        missing = sorted(set(requested) - existing)
        if missing:
            raise ValueError(f"traffic names missing deployments: {', '.join(missing)}")
        endpoint_state = client.online_endpoints.get(endpoint)
        endpoint_state.traffic = requested
        client.online_endpoints.begin_create_or_update(endpoint_state).result()
        observed = dict(client.online_endpoints.get(endpoint).traffic or {})
        if observed != requested:
            raise RuntimeError(f"traffic verification failed: expected {requested}, got {observed}")
        return observed

    def get_model_tags(self, name: str, version: str) -> dict[str, str]:
        model = self._ml_client().models.get(name=name, version=version)
        return dict(model.tags or {})

    def register_model(
        self, model_uri: str, name: str, tags: dict[str, str]
    ) -> str:
        """Register an MLflow job artifact without requiring the MLflow Azure plugin."""
        if not model_uri.startswith("runs:/"):
            raise ValueError("model_uri must be runs:/<run-id>/<artifact>")
        value = model_uri.removeprefix("runs:/").strip("/")
        run_id, separator, artifact_path = value.partition("/")
        if not separator or not run_id or not artifact_path:
            raise ValueError("model_uri must include an artifact path")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
            raise ValueError("unsafe run id")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", artifact_path):
            raise ValueError("unsafe artifact path")
        from azure.ai.ml.constants import AssetTypes
        from azure.ai.ml.entities import Model

        registered = self._ml_client().models.create_or_update(
            Model(
                path=f"azureml://jobs/{run_id}/outputs/artifacts/paths/{artifact_path}/",
                name=name,
                type=AssetTypes.MLFLOW_MODEL,
                tags=tags,
                description="ITCS355 Lab 3 measured canary candidate",
            )
        )
        if not registered.version:
            raise RuntimeError("Azure did not return a registered model version")
        return str(registered.version)

    def delete_deployment(
        self, endpoint: str, deployment: str, required_tags: dict[str, str]
    ) -> bool:
        """Delete one non-production deployment only when all ownership tags match."""
        if deployment == "blue":
            raise ValueError("refusing to delete the production deployment")
        from azure.core.exceptions import ResourceNotFoundError

        client = self._ml_client()
        try:
            existing = client.online_deployments.get(
                name=deployment, endpoint_name=endpoint
            )
        except ResourceNotFoundError:
            return False
        tags = existing.tags or {}
        if any(tags.get(key) != value for key, value in required_tags.items()):
            raise RuntimeError("refusing deployment deletion because tags do not match")
        client.online_deployments.begin_delete(
            name=deployment, endpoint_name=endpoint
        ).result()
        return True

    def endpoint_exists(self, endpoint: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._ml_client().online_endpoints.get(endpoint)
        except ResourceNotFoundError:
            return False
        return True

    def teardown(self, tags: dict[str, str]) -> list[str]:
        if tags.get("lab") != "3":
            raise ValueError("Lab 3 teardown requires lab=3")
        from azure.core.exceptions import ResourceNotFoundError

        client = self._ml_client()
        try:
            endpoint = client.online_endpoints.get(self.cfg.online_endpoint)
        except ResourceNotFoundError:
            return []
        endpoint_tags = endpoint.tags or {}
        if any(endpoint_tags.get(key) != value for key, value in tags.items()):
            raise RuntimeError("refusing teardown because endpoint tags do not match")
        client.online_endpoints.begin_delete(name=self.cfg.online_endpoint).result()
        return [f"deleted endpoint:{self.cfg.online_endpoint}"]
