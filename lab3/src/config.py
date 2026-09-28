"""Typed environment configuration for Lab 3."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "cloud.env"


def _load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


@dataclass(frozen=True)
class Config:
    provider: str
    project_id: str
    region: str
    azure_subscription_id: str
    azure_resource_group: str
    azureml_workspace: str
    container_registry: str
    model_registry_name: str
    model_version: str
    serving_image_uri: str
    online_endpoint: str
    target_concurrency: int
    deployment_name: str = "blue"
    serving_instance: str = "Standard_DS2_v2"
    reports_dir: Path = field(default=REPO_ROOT / "reports")

    def tags(self, lab: int = 3) -> dict[str, str]:
        return {"course": "itcs355", "student": self.project_id, "lab": str(lab)}


def load(strict: bool = True) -> Config:
    get = os.environ.get
    values = {
        "provider": get("CLOUD_PROVIDER", "azure"),
        "project_id": get("PROJECT_ID", "6688012"),
        "region": get("REGION", "centralindia"),
        "azure_subscription_id": get("AZURE_SUBSCRIPTION_ID", ""),
        "azure_resource_group": get("AZURE_RESOURCE_GROUP", ""),
        "azureml_workspace": get("AZUREML_WORKSPACE", ""),
        "container_registry": get("CONTAINER_REGISTRY", ""),
        "model_registry_name": get("MODEL_REGISTRY_NAME", "itcs355-6688012"),
        "model_version": get("MODEL_VERSION", "1"),
        "serving_image_uri": get("SERVING_IMAGE_URI", ""),
        "online_endpoint": get("ONLINE_ENDPOINT", "itcs355-6688012-lab3"),
        "target_concurrency": int(get("TARGET_CONCURRENCY", "10")),
        "deployment_name": get("DEPLOYMENT_NAME", "blue"),
        "serving_instance": get("SERVING_INSTANCE", "Standard_DS2_v2"),
    }
    required = (
        "azure_subscription_id",
        "azure_resource_group",
        "azureml_workspace",
        "container_registry",
    )
    missing = [name for name in required if not values[name]]
    if strict and missing:
        labels = ", ".join(name.upper() for name in missing)
        raise RuntimeError(f"Missing Lab 3 configuration: {labels}")
    if values["target_concurrency"] < 1:
        raise ValueError("TARGET_CONCURRENCY must be a positive integer")
    return Config(**values)
