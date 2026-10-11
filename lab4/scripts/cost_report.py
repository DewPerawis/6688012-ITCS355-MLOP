"""Estimate only from observed timestamps and explicitly supplied current prices."""
import argparse
import json
from datetime import datetime
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serving-hourly-thb", type=float)
    parser.add_argument("--monitor-hourly-thb", type=float)
    parser.add_argument("--monitor-hours", type=float, help="sum of measured scheduled-job instance runtimes")
    parser.add_argument("--price-source", help="current source URL, SKU, region and retrieval time")
    args = parser.parse_args()
    deployment, teardown = Path("reports/lab4-deployment.json"), Path("reports/lab4-teardown.json")
    if (not deployment.is_file() or not teardown.is_file()
            or any(value is None for value in (args.serving_hourly_thb, args.monitor_hourly_thb,
                                               args.monitor_hours)) or not args.price_source):
        result = {"status": "pending_measured_inputs", "cost_thb": None,
                  "required": ["deployment/verified teardown JSON", "current serving/monitor SKU prices",
                               "measured monitor runtime", "price source and retrieved-at time"],
                  "billing": "record actual Azure Cost Management in lab4-cost.md"}
    else:
        if min(args.serving_hourly_thb, args.monitor_hourly_thb, args.monitor_hours) < 0:
            parser.error("prices and runtimes must be nonnegative")
        begin = json.loads(deployment.read_text())
        end = json.loads(teardown.read_text())
        hours = (datetime.fromisoformat(end["verified_at"])
                 - datetime.fromisoformat(begin.get("deployment_started_at", begin["deployed_at"]))).total_seconds() / 3600
        if hours < 0:
            raise ValueError("teardown precedes deployment")
        result = {"status": "compute_estimate_only", "serving_observed_hours": hours,
                  "monitor_measured_hours": args.monitor_hours,
                  "compute_estimate_thb": hours * args.serving_hourly_thb
                                          + args.monitor_hours * args.monitor_hourly_thb,
                  "price_source": args.price_source,
                  "limitations": "observed wall-clock envelope is not billed VM runtime; excludes logs, storage, registry and tax",
                  "actual_billed_thb": None}
    Path("reports/cost-estimate.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
