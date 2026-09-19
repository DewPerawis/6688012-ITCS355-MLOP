"""Create or verify the Azure ML workspace, datastore and dedicated compute.

This script is intentionally separate from job submission: creating cloud resources is a
visible decision. The compute cluster scales to zero and has one-node maximum.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure.ai.ml import MLClient
from azure.ai.ml.constants import ManagedServiceIdentityType
from azure.ai.ml.entities import (
    AmlCompute,
    AzureBlobDatastore,
    IdentityConfiguration,
    Workspace,
)
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

from cloudlayer.azure import (
    BLOB_DATA_CONTRIBUTOR_ROLE,
    _acr_resource_id,
    _blob_location,
    _ensure_role_assignment,
)
from src import config


def _resource_id(subscription: str, group: str, provider: str, resource_type: str, name: str) -> str:
    return (
        f"/subscriptions/{subscription}/resourceGroups/{group}/providers/"
        f"{provider}/{resource_type}/{name}"
    )


def _dedicated_compute(name: str, tags: dict[str, str]) -> AmlCompute:
    """Build the scale-to-zero compute spec with an identity for private ACR pulls."""
    return AmlCompute(
        name=name,
        size="Standard_DS2_v2",
        min_instances=0,
        max_instances=1,
        idle_time_before_scale_down=120,
        tier="dedicated",
        identity=IdentityConfiguration(type=ManagedServiceIdentityType.SYSTEM_ASSIGNED),
        tags=tags,
    )


def main() -> int:
    cfg = config.load()
    if cfg.provider.lower() != "azure":
        raise RuntimeError("bootstrap_azureml.py is only valid for CLOUD_PROVIDER=azure")
    if not cfg.azure_subscription_id:
        raise RuntimeError("set AZURE_SUBSCRIPTION_ID in cloud.env")

    account_url, container, prefix = _blob_location(cfg.blob_uri)
    storage_name = account_url.removeprefix("https://").split(".", 1)[0]
    storage_id = _resource_id(
        cfg.azure_subscription_id,
        cfg.azure_resource_group,
        "Microsoft.Storage",
        "storageAccounts",
        storage_name,
    )
    registry_host = cfg.container_registry.split("/", 1)[0]
    credential = DefaultAzureCredential()

    subscription_client = MLClient(
        credential,
        cfg.azure_subscription_id,
        cfg.azure_resource_group,
    )
    try:
        workspace = subscription_client.workspaces.get(cfg.azureml_workspace)
        workspace_action = "verified"
    except ResourceNotFoundError:
        workspace_spec = Workspace(
            name=cfg.azureml_workspace,
            location=cfg.region,
            description="ITCS355 Lab 2 experiment tracking and model registry",
            tags=cfg.tags(2),
            storage_account=storage_id,
            container_registry=_acr_resource_id(registry_host),
        )
        workspace = subscription_client.workspaces.begin_create(workspace_spec).result()
        workspace_action = "created"

    client = MLClient(
        credential,
        cfg.azure_subscription_id,
        cfg.azure_resource_group,
        cfg.azureml_workspace,
    )
    datastore = AzureBlobDatastore(
        name="itcs355blob",
        description="Identity-based access to the course Blob container",
        account_name=storage_name,
        container_name=container,
        protocol="https",
        tags=cfg.tags(2),
    )
    datastore = client.datastores.create_or_update(datastore)

    compute_spec = _dedicated_compute(cfg.training_target, cfg.tags(2))
    compute = client.compute.begin_create_or_update(compute_spec).result()

    compute_identity = getattr(compute, "identity", None)
    compute_identity_type = getattr(compute_identity, "type", None)
    compute_principal_id = getattr(compute_identity, "principal_id", None)
    if not compute_principal_id:
        raise RuntimeError("Azure ML compute returned no managed-identity principal ID")

    container_scope = f"{storage_id}/blobServices/default/containers/{container}"
    storage_role_action = _ensure_role_assignment(
        compute_principal_id,
        BLOB_DATA_CONTRIBUTOR_ROLE,
        container_scope,
    )

    evidence = {
        "workspace": workspace.name,
        "workspace_action": workspace_action,
        "location": workspace.location,
        "tracking_uri_configured": bool(workspace.mlflow_tracking_uri),
        "datastore": datastore.name,
        "blob_prefix": prefix,
        "compute": compute.name,
        "compute_size": compute.size,
        "compute_tier": compute.tier,
        "compute_identity_type": str(compute_identity_type),
        "compute_principal_configured": True,
        "compute_storage_role": BLOB_DATA_CONTRIBUTOR_ROLE,
        "compute_storage_role_action": storage_role_action,
        "compute_storage_scope": f"container:{container}",
        "min_instances": compute.min_instances,
        "max_instances": compute.max_instances,
    }
    out = cfg.reports_dir / "azureml-bootstrap.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True))
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
