"""Generate an importable Azure Workbook with gateway and container signals."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from src import config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="historical UTC window start, ISO 8601")
    parser.add_argument("--end", help="historical UTC window end, ISO 8601")
    args = parser.parse_args()
    if bool(args.start) != bool(args.end):
        parser.error("provide both --start and --end")
    historical = bool(args.start)
    if historical:
        start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
        end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            parser.error("use timezone-aware start before end")
    cfg = config.load(strict=False)
    scope = os.getenv("LOG_ANALYTICS_RESOURCE_ID", "<LOG_ANALYTICS_RESOURCE_ID>")
    endpoint = cfg.online_endpoint
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in endpoint):
        raise ValueError("invalid endpoint")
    traffic = f'AmlOnlineEndpointTrafficLog | where EndpointName == "{endpoint}"'
    console = ('AmlOnlineEndpointConsoleLog | extend e=parse_json(Message) '
               f'| where e.endpoint == "{endpoint}"')
    if historical:
        time_filter = f' | where TimeGenerated between (datetime({start.isoformat()})..datetime({end.isoformat()}))'
        traffic += time_filter
        console += time_filter
        event_filter = f' | where EventTime between (datetime({(start - timedelta(minutes=4)).isoformat()})..datetime({end.isoformat()}))'
        bucket_filter = f' | where Buckets between (datetime({start.isoformat()})..datetime({end.isoformat()}))'
    else:
        event_filter = ' | where EventTime > ago(35m)'
        bucket_filter = ' | where Buckets between (ago(30m)..now())'
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
         + event_filter
         + ' '
           '| extend Buckets=range(bin(EventTime,1m),bin(EventTime,1m)+4m,1m) '
           '| mv-expand Buckets to typeof(datetime) '
         + bucket_filter
         + ' '
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
            "crossComponentResources": [scope], "timeContext": {"durationMs": 86400000 if historical else 1800000},
            "visualization": "table" if index == 5 else "timechart"}})
    workbook = {"version": "Notebook/1.0", "items": items, "isLocked": False,
                "fallbackResourceIds": [scope]}
    suffix = "-evidence" if historical else ""
    if historical:
        items[0]["content"]["json"] = (
            "# ITCS355 Lab 4 — historical cloud evidence\n"
            f"UTC window: {start.isoformat()} to {end.isoformat()}. "
            "Queries read retained Azure logs after teardown; no service is restarted. "
            "The workbook query scope is the last 24 hours; capture this exercise within that scope."
        )
    Path(f"monitoring/workbook{suffix}.json").write_text(json.dumps(workbook, indent=2), encoding="utf-8")
    Path(f"monitoring/queries{suffix}.kql").write_text("\n\n".join(
        f"// {title}\n{query}" for title, query in queries), encoding="utf-8")
    print(f"Generated monitoring/workbook{suffix}.json and monitoring/queries{suffix}.kql")
    if scope.startswith("<"):
        print("Set LOG_ANALYTICS_RESOURCE_ID in cloud.env and regenerate before importing")


if __name__ == "__main__":
    main()
