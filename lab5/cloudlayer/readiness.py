"""Read-only Azure inspection. No resource creation or credential export."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
CONFIG_KEYS = (
    "CLOUD_PROVIDER", "PROJECT_ID", "REGION", "AZURE_SUBSCRIPTION_ID",
    "AZURE_RESOURCE_GROUP", "AZUREML_WORKSPACE", "CONTAINER_REGISTRY",
    "MODEL_REGISTRY_NAME", "MODEL_VERSION",
)


def inherited_config():
    """Read only identifiers; never evaluate shell or print complete env files."""
    import os

    values, sources = {}, []
    for relative in ("lab2/cloud.env", "lab3/cloud.env", "lab4/cloud.env", "lab5/cloud.env"):
        path = REPO / relative
        if not path.is_file():
            continue
        sources.append(relative)
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = raw.strip().partition("=")
            key = key.strip()
            if separator and key in CONFIG_KEYS:
                value = value.strip()
                if value[:1] in ("'", '"') and value[-1:] == value[:1]:
                    value = value[1:-1]
                else:
                    value = value.split(" #", 1)[0].rstrip()
                if value:
                    values[key] = value
    for key in CONFIG_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    values.setdefault("CLOUD_PROVIDER", "azure")
    values.setdefault("PROJECT_ID", "6688012")
    values.setdefault("MODEL_REGISTRY_NAME", "itcs355-6688012")
    values.setdefault("MODEL_VERSION", "1")
    if values["CLOUD_PROVIDER"].lower() != "azure":
        raise ValueError("This exercise continues on Azure; check CLOUD_PROVIDER overrides.")
    required = ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZUREML_WORKSPACE", "REGION")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError("Missing identifiers: " + ", ".join(missing)
                         + ". Check the ignored cloud.env from your previous Lab.")
    return values, sources


def cli_json(arguments):
    completed = subprocess.run(
        ["az", *arguments, "--only-show-errors", "-o", "json"],
        text=True, capture_output=True, timeout=90, check=False,
    )
    if completed.returncode:
        # CLI stderr is not persisted: it can include request details.
        raise RuntimeError("Azure CLI read failed. Check az login/account and resource access.")
    return json.loads(completed.stdout)


def model_summary(model):
    # Tags from older jobs can contain arbitrary user content; retain lineage only.
    allowed = ("git_commit", "data_version", "mlflow_run_id", "training_job_id",
               "image_digest", "seed", "metric_val", "metric_test", "stage")
    return {"name": model.name, "version": str(model.version),
            "type": str(model.type),
            "lineage": {key: value for key, value in (model.tags or {}).items() if key in allowed}}


def quota_summary(item):
    """SDK 1.35.0 copies REST dicts into Usage, leaving nested name as a dict."""
    def field(value, name):
        return value.get(name) if isinstance(value, dict) else getattr(value, name, None)

    name = field(item, "name")
    value = field(name, "value")
    current = field(item, "current_value")
    if current is None:
        current = field(item, "currentValue")
    limit = field(item, "limit")
    if not isinstance(value, str) or not value or current is None or limit is None:
        raise ValueError("Quota response has missing fields; do not treat missing values as zero.")
    return {"name": value, "current": current, "limit": limit,
            "unit": str(field(item, "unit") or "unknown")}


def inspect_workspace(cfg, progress, record):
    from azure.ai.ml import MLClient
    from azure.identity import AzureCliCredential

    subscription = cfg["AZURE_SUBSCRIPTION_ID"]
    account = cli_json(["account", "show", "--subscription", subscription,
                        "--query", "{state:state,name:name,id:id}"])
    if account.get("state") != "Enabled" or account.get("id", "").lower() != subscription.lower():
        raise RuntimeError("Configured subscription is not Enabled or does not match the CLI response.")
    record["account"] = {"name": account["name"], "state": account["state"]}
    client = MLClient(
        AzureCliCredential(subscription=subscription), subscription,
        cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
        enable_telemetry=False, connection_timeout=20, read_timeout=60, retry_total=1,
    )
    progress("Read workspace and exact incumbent model")
    workspace = client.workspaces.get(cfg["AZUREML_WORKSPACE"])
    record["workspace"] = {"name": workspace.name, "location": workspace.location}
    model = client.models.get(cfg["MODEL_REGISTRY_NAME"], cfg["MODEL_VERSION"])
    record["incumbent"] = model_summary(model)

    # Optional inspections are kept distinct from the required workspace/model check.
    checks = {
        "compute": lambda: [
            {"name": item.name, "type": str(item.type), "size": getattr(item, "size", None),
             "min_instances": getattr(item, "min_instances", None),
             "max_instances": getattr(item, "max_instances", None)}
            for item in client.compute.list()],
        "endpoints": lambda: [
            {"name": item.name, "state": str(item.provisioning_state)}
            for item in client.online_endpoints.list()],
        "schedules": lambda: [
            {"name": item.name, "enabled": item.is_enabled}
            for item in client.schedules.list()],
        "quota": lambda: [quota_summary(item)
                          for item in client.compute.list_usage(location=workspace.location)],
        "resource_inventory": lambda: cli_json([
            "resource", "list", "--subscription", subscription,
            "--resource-group", cfg["AZURE_RESOURCE_GROUP"],
            "--query", "[].{name:name,type:type,location:location}"]),
    }
    for name, inspect in checks.items():
        progress("Read " + name)
        try:
            record[name] = {"status": "ok", "items": inspect()}
        except Exception as exc:
            record[name] = {"status": "unavailable", "error_type": type(exc).__name__}
    record["quota_note"] = "Quota visibility does not guarantee SKU capacity or Spot availability."


def retail_prices(region, sku="Standard_DS2_v2"):
    """Collect current meters without silently choosing Windows, Spot or a plan price."""
    if not re.fullmatch(r"[a-z0-9]+", region) or not re.fullmatch(r"[A-Za-z0-9_]+", sku):
        raise ValueError("Unexpected region or SKU format")
    query = {
        "currencyCode": "'THB'",
        "$filter": (f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
                    f"and armSkuName eq '{sku}' and priceType eq 'Consumption'"),
    }
    url = "https://prices.azure.com/api/retail/prices?" + urlencode(query)
    source, meters, seen = url, [], set()
    while url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "prices.azure.com" or url in seen:
            raise RuntimeError("Invalid pricing pagination URL")
        seen.add(url)
        with urlopen(url, timeout=30) as response:
            payload = json.load(response)
        for item in payload.get("Items", []):
            meters.append({key: item.get(key) for key in (
                "meterId", "meterName", "productName", "skuName", "armSkuName", "armRegionName",
                "retailPrice", "unitOfMeasure", "currencyCode", "type", "effectiveStartDate",
                "isPrimaryMeterRegion", "tierMinimumUnits",
            )})
        url = payload.get("NextPageLink")
    return {"retrieved_at": datetime.now(timezone.utc).isoformat(), "source": source,
            "sku": sku, "region": region, "meters": meters,
            "note": "Retail VM reference only; not the Azure Students invoice or an ML service quote. "
                    "THB prices are budget references. Select the correct Linux meter before estimating."}
