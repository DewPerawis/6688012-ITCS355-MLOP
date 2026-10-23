"""Read-only quota, identity inventory and Cost Management observations."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cloudlayer.readiness import cli_json, quota_summary


class BillingThrottled(RuntimeError):
    def __init__(self, delay, headers):
        super().__init__("Cost Management throttled; billing is pending, not zero.")
        self.retry_after_seconds = delay
        self.retry_headers = headers


def retry_delay(headers):
    """Honor the longest applicable Cost Management throttle, not just Retry-After."""
    values = {key.lower(): value for key, value in headers.items()
              if key.lower() == "retry-after" or (
                  key.lower().startswith("x-ms-ratelimit-") and key.lower().endswith("retry-after"))}
    delays = []
    for value in values.values():
        try:
            delay = float(value)
        except (TypeError, ValueError):
            try:
                delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                continue
        if delay >= 0:
            delays.append(delay)
    return max(delays, default=30), values


def cost_response(request, progress=print):
    """At most three attempts. Long server cooldowns are returned for a later rerun."""
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code != 429:
                raise
            delay, headers = retry_delay(exc.headers)
            exc.close()
            if attempt == 2 or delay > 60:
                raise BillingThrottled(delay, headers) from None
            # Minimum backoff prevents tight retries when a header says zero.
            remaining = max(1, delay)
            progress(f"Billing HTTP 429: wait {remaining:g}s before attempt {attempt + 2}/3")
            while remaining > 0:
                pause = min(10, remaining)
                time.sleep(pause)
                remaining -= pause
                if remaining > 0:
                    progress(f"Billing cooldown: {remaining:g}s remaining")


def inspect_quota(cfg):
    from azure.ai.ml import MLClient
    from azure.identity import AzureCliCredential

    client = MLClient(
        AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
        cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
        enable_telemetry=False, connection_timeout=20, read_timeout=60, retry_total=1,
    )
    items = [quota_summary(item) for item in client.compute.list_usage(location=cfg["REGION"])]
    relevant = [row for row in items if any(text in row["name"].lower()
                for text in ("dsv2", "dedicated", "lowpriority", "low_priority", "total"))]
    return {"status": "ok", "region": cfg["REGION"], "items": items,
            "relevant": relevant,
            "note": "Subscription/region ML quota only. This does not prove SKU capacity, "
                    "role permissions, endpoint quota or discounted-compute eligibility."}


def inspect_identities(cfg):
    return cli_json(["identity", "list", "--subscription", cfg["AZURE_SUBSCRIPTION_ID"],
                     "--resource-group", cfg["AZURE_RESOURCE_GROUP"],
                     "--query", "[].{name:name,principalId:principalId,location:location}"])


def billing_observation(cfg, since="2026-09-01", lab5_only=False, progress=print):
    """Query posted charges at the course RG scope; do not infer unposted charges are zero."""
    from azure.identity import AzureCliCredential

    datetime.strptime(since, "%Y-%m-%d")
    now = datetime.now(timezone.utc)
    if since > now.strftime("%Y-%m-%d"):
        raise ValueError("Billing observation start cannot be in the future")
    subscription, group = cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"]
    if not re.fullmatch(r"[A-Fa-f0-9-]{36}", subscription) or not re.fullmatch(r"[\w.()-]+", group):
        raise ValueError("Unexpected resource scope identifiers")
    url = (f"https://management.azure.com/subscriptions/{subscription}/resourceGroups/{group}"
           "/providers/Microsoft.CostManagement/query?api-version=2025-03-01")
    body = {"type": "ActualCost", "timeframe": "Custom",
            "timePeriod": {"from": since + "T00:00:00Z", "to": now.isoformat()},
            "dataset": {"aggregation": {
                "totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                "grouping": [{"type": "Dimension", "name": "ResourceId"}]}}
    if lab5_only:
        body["dataset"]["filter"] = {"and": [
            {"tags": {"name": "student", "operator": "In", "values": [cfg["PROJECT_ID"]]}},
            {"tags": {"name": "lab", "operator": "In", "values": ["5"]}},
        ]}
    token = AzureCliCredential(subscription=subscription).get_token(
        "https://management.azure.com/.default").token
    pages, rows, columns, visited = 0, [], None, set()
    while url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "management.azure.com" or url in visited:
            raise RuntimeError("Unexpected billing pagination URL")
        visited.add(url)
        request = Request(url, data=json.dumps(body).encode(), method="POST",
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        raw = cost_response(request, progress=progress)
        payload = json.loads(raw) if raw else {"properties": {"columns": [], "rows": []}}
        props = payload["properties"]
        page_columns = [column["name"] for column in props.get("columns", [])]
        if columns is not None and columns != page_columns:
            raise ValueError("Billing columns changed between pages")
        columns = page_columns
        rows.extend(props.get("rows", []))
        url = props.get("nextLink")
        pages += 1
    totals, by_resource = {}, []
    for row in rows:
        entry = dict(zip(columns or [], row))
        cost = entry.get("PreTaxCost", entry.get("totalCost"))
        if cost is None or not entry.get("Currency"):
            raise ValueError("Billing cost/currency fields are missing")
        currency = entry["Currency"]
        totals[currency] = totals.get(currency, 0.0) + float(cost)
        resource = entry.get("ResourceId", "")
        # Keep names/types for reconciliation without publishing the subscription GUID.
        parts = resource.split("/providers/", 1)
        by_resource.append({"resource": parts[-1] if len(parts) == 2 else "unclassified",
                            "cost": float(cost), "currency": currency})
    return {"status": "ok", "queried_at": now.isoformat(), "from": since,
            "to": now.isoformat(), "scope": "course resource group",
            "lab5_tag_filter": lab5_only, "pages": pages, "rows": by_resource,
            "posted_totals_by_currency": totals,
            "note": "Posted pretax charges only. Empty rows are not proof of free usage. "
                    "The unfiltered group includes shared earlier-lab resources. This is an "
                    "observation window, not a verified full-term total; FX/late charges/other scopes remain pending."}
