"""Azure APIs for recent service inputs and Key Vault; no SDK in monitoring/."""
from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

from azure.identity import DefaultAzureCredential


def _json_request(url: str, scope: str, body: dict | None = None) -> dict:
    token = DefaultAzureCredential().get_token(scope).token
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=payload,
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def query_logs(workspace_id: str, query: str, timespan: str = "PT30M") -> list[dict]:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", workspace_id):
        raise ValueError("LOG_ANALYTICS_WORKSPACE_ID must be a workspace customer GUID")
    result = _json_request(f"https://api.loganalytics.azure.com/v1/workspaces/{workspace_id}/query",
                           "https://api.loganalytics.io/.default",
                           {"query": query, "timespan": timespan})
    if result.get("error"):
        raise RuntimeError("Log Analytics query failed or returned partial data")
    if not result.get("tables"):
        return []
    table = result["tables"][0]
    names = [item["name"] for item in table["columns"]]
    return [dict(zip(names, row, strict=True)) for row in table["rows"]]


def recent_inputs(workspace_id: str, endpoint: str, version: str, rows: int = 500,
                  minutes: int = 15) -> list[dict]:
    if not re.fullmatch(r"[a-z0-9-]+", endpoint) or not version.isdigit():
        raise ValueError("invalid endpoint or exact model version")
    if not 1 <= rows <= 50000 or not 1 <= minutes <= 1440:
        raise ValueError("invalid monitoring window")
    query = f'''AmlOnlineEndpointConsoleLog
| where TimeGenerated > ago({minutes}m)
| extend e = parse_json(Message)
| where e.event == "prediction_features" and e.endpoint == "{endpoint}"
| where tostring(e.model_version) == "{version}"
| extend EventTime=todatetime(e.timestamp)
| where EventTime > ago({minutes}m)
| top {rows} by EventTime desc
| project timestamp=tostring(e.timestamp), features=e.features'''
    return query_logs(workspace_id, query, f"PT{minutes + 15}M")


def secret_value(vault_url: str, secret_name: str) -> str:
    if not re.fullmatch(r"https://[a-zA-Z0-9-]+\.vault\.azure\.net/?", vault_url):
        raise ValueError("VAULT_URL must be an Azure Key Vault HTTPS URL")
    if not re.fullmatch(r"[a-zA-Z0-9-]+", secret_name):
        raise ValueError("invalid secret name")
    result = _json_request(f"{vault_url.rstrip('/')}/secrets/{secret_name}?api-version=7.4",
                           "https://vault.azure.net/.default")
    return str(result["value"])
