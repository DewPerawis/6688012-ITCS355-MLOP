"""Check recent logged inputs before starting paid monitoring jobs."""
import json
import os
from pathlib import Path

from cloudlayer.observability import query_logs, recent_inputs
from src import config

if __name__ == "__main__":
    cfg = config.load()
    rows = recent_inputs(os.environ["LOG_ANALYTICS_WORKSPACE_ID"],
                         cfg.online_endpoint, cfg.model_version)
    result = {"endpoint": cfg.online_endpoint, "model_version": cfg.model_version,
              "recent_feature_rows": len(rows), "required_rows": 500,
              "ready": len(rows) >= 500}
    Path("reports/monitor-input-readiness.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["ready"]:
        summary = query_logs(os.environ["LOG_ANALYTICS_WORKSPACE_ID"], f'''AmlOnlineEndpointConsoleLog
| where TimeGenerated > ago(1h)
| extend e = parse_json(Message)
| summarize console_rows=count(),
    prediction_events=countif(e.event == "prediction_features"),
    matching_events=countif(e.event == "prediction_features" and e.endpoint == "{cfg.online_endpoint}"
        and tostring(e.model_version) == "{cfg.model_version}"),
    newest_event=max(todatetime(e.timestamp)), newest_log=max(TimeGenerated)''', "PT1H")
        print("Log ingestion diagnostics (last hour):")
        print(json.dumps(summary, indent=2))
        print("Wait for log ingestion and replay baseline again before starting monitoring jobs.")
