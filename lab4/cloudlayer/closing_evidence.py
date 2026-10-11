"""Read-only dashboard export, current retail prices, and billing observations."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from cloudlayer.observability import _json_request, query_logs
from src import config


def save(name, result):
    Path(f"reports/{name}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    cfg = config.load()

    queries = Path("monitoring/queries-evidence.kql").read_text().strip().split("\n\n")
    dashboard = []
    for block in queries:
        title, query = block.split("\n", 1)
        rows = query_logs(os.environ["LOG_ANALYTICS_WORKSPACE_ID"], query,
                          "2026-10-11T22:00:00Z/2026-10-11T23:10:00Z")
        dashboard.append({"title": title.removeprefix("// "), "query": query, "rows": rows})
    save("dashboard-cloud-data", {"source": "Azure Log Analytics", "panels": dashboard})
    print("Retained dashboard data:", [(p["title"], len(p["rows"])) for p in dashboard], flush=True)

    prices = []
    for sku in ("Standard_DS2_v2", "Standard_DS1_v2"):
        filters = f"serviceName eq 'Virtual Machines' and armRegionName eq '{cfg.region}' and armSkuName eq '{sku}'"
        url = "https://prices.azure.com/api/retail/prices?" + urlencode({"$filter": filters})
        with urlopen(url, timeout=60) as response:
            items = json.load(response)["Items"]
        candidates = [item for item in items if item["type"] == "Consumption"
                      and item["unitOfMeasure"] == "1 Hour"
                      and "windows" not in item["productName"].lower()
                      and not any(word in item["meterName"].lower() for word in ("spot", "low priority"))]
        prices.append({"sku": sku, "source": url, "candidates": candidates})
    save("retail-prices", {"retrieved_at": datetime.now(UTC).isoformat(), "prices": prices,
                           "limitation": "Public retail reference; not the Azure Students invoice price."})
    print("Price candidates:", [(p["sku"], len(p["candidates"])) for p in prices], flush=True)

    scope = f"subscriptions/{cfg.azure_subscription_id}/resourceGroups/{cfg.azure_resource_group}"
    url = f"https://management.azure.com/{scope}/providers/Microsoft.CostManagement/query?api-version=2025-03-01"
    body = {"type": "ActualCost", "timeframe": "Custom",
            "timePeriod": {"from": "2026-10-11T00:00:00Z", "to": "2026-10-12T23:59:59Z"},
            "dataset": {"granularity": "Daily", "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                        "grouping": [{"type": "Dimension", "name": "ResourceId"}]}}
    try:
        result = _json_request(url, "https://management.azure.com/.default", body)
        save("billing-observation", {"queried_at": datetime.now(UTC).isoformat(), "scope": scope,
                                     "response": result, "limitation": "Resource-group observations include shared earlier-lab resources; recent usage may not be posted yet."})
        print("Billing returned rows:", len(result.get("properties", {}).get("rows", [])))
    except HTTPError as error:
        save("billing-observation", {"queried_at": datetime.now(UTC).isoformat(), "http_status": error.code,
                                     "status": "unavailable", "actual_lab4_cost": None})
        print("Billing query unavailable, HTTP", error.code)

    from azure.core.exceptions import ResourceNotFoundError

    from cloudlayer.factory import get_adapter

    client = get_adapter(cfg)._ml_client()
    remaining = {}
    for kind, operations, name in (("endpoint", client.online_endpoints, cfg.online_endpoint),
                                    ("schedule", client.schedules, os.environ["DRIFT_SCHEDULE"]),
                                    ("compute", client.compute, os.environ["MONITOR_COMPUTE"])):
        try:
            operations.get(name)
            remaining[kind] = name
        except ResourceNotFoundError:
            pass
    save("final-cloud-check", {"checked_at": datetime.now(UTC).isoformat(), "remaining": remaining})
    pipeline = "itcs355-6688012-lab4-drift-08584098484054611101308887078CU10"
    job = client.jobs.get(pipeline)
    save("scheduled-run", {"name": job.name, "status": job.status,
                           "run_source": job.properties.get("runSource"),
                           "schedule": job.properties.get("azureml.genericTriggerName"),
                           "properties": {k: v for k, v in job.properties.items()
                                          if k in ("azureml.pipelines.stages", "azureml.enforceRerun")}})
    print("Final resources remaining:", remaining, "; scheduled proof:", job.status)


if __name__ == "__main__":
    main()
