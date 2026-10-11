"""Generate an importable Azure Workbook with gateway and container signals."""
from __future__ import annotations

import json
import os
from pathlib import Path

from src import config


def main():
    cfg = config.load(strict=False)
    scope = os.getenv("LOG_ANALYTICS_RESOURCE_ID", "<LOG_ANALYTICS_RESOURCE_ID>")
    endpoint = cfg.online_endpoint
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in endpoint):
        raise ValueError("invalid endpoint")
    traffic = f'AmlOnlineEndpointTrafficLog | where EndpointName == "{endpoint}"'
    console = ('AmlOnlineEndpointConsoleLog | extend e=parse_json(Message) '
               f'| where e.endpoint == "{endpoint}"')
    queries = [
        ("Request rate (requests/second)", traffic
         + ' | summarize RequestsPerSecond=count()/60.0 by bin(TimeGenerated,1m)'),
        ("4xx and 5xx error fractions", traffic
         + ' | summarize Total=count(), Client=countif(toint(ResponseCode) between (400..499)), '
           'Server=countif(toint(ResponseCode)>=500) by bin(TimeGenerated,1m) '
           '| project TimeGenerated, Error4xx=todouble(Client)/Total, Error5xx=todouble(Server)/Total'),
        ("Gateway latency p50 / p95 / p99 (ms)", traffic
         + ' | summarize p50=percentile(TotalDurationMs,50), p95=percentile(TotalDurationMs,95), '
           'p99=percentile(TotalDurationMs,99) by bin(TimeGenerated,1m)'),
        ("temp_c mean, rolling 5-minute window", console
         + ' | where e.event == "prediction_features" '
           '| extend EventTime=todatetime(e.timestamp), Temperature=todouble(e.features.temp_c) '
           '| where EventTime > ago(35m) '
           '| extend Buckets=range(bin(EventTime,1m),bin(EventTime,1m)+4m,1m) '
           '| mv-expand Buckets to typeof(datetime) '
           '| where Buckets between (ago(30m)..now()) '
           '| summarize MeanTemperature=avg(Temperature), FeatureRows=count() by TimeGenerated=Buckets'),
        ("Current model versions", console
         + ' | where e.event == "request" and e.path in ("/predict","/predict/batch","/invoke") '
           '| summarize LastSeen=max(TimeGenerated), Requests=count() by ModelVersion=tostring(e.model_version)'),
    ]
    items = [{"type": 1, "name": "intro", "content": {"json":
        "# ITCS355 Lab 4\nLive Azure staging telemetry. Gateway latency includes serving gateway; "
        "local /metrics measures the application only. Drift PSI metrics are in the scheduled Azure ML job."}}]
    for index, (title, query) in enumerate(queries, 1):
        items.append({"type": 3, "name": f"panel-{index}", "content": {
            "version": "KqlItem/1.0", "title": title, "query": query,
            "size": 0, "queryType": 0, "resourceType": "microsoft.operationalinsights/workspaces",
            "crossComponentResources": [scope], "timeContext": {"durationMs": 1800000},
            "visualization": "table" if index == 5 else "timechart"}})
    workbook = {"version": "Notebook/1.0", "items": items, "isLocked": False,
                "fallbackResourceIds": [scope]}
    Path("monitoring/workbook.json").write_text(json.dumps(workbook, indent=2), encoding="utf-8")
    Path("monitoring/queries.kql").write_text("\n\n".join(
        f"// {title}\n{query}" for title, query in queries), encoding="utf-8")
    print("Generated monitoring/workbook.json and monitoring/queries.kql")
    if scope.startswith("<"):
        print("Set LOG_ANALYTICS_RESOURCE_ID in cloud.env and regenerate before importing")


if __name__ == "__main__":
    main()
