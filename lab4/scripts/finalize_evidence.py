"""Compute detection time from captured cloud evidence; refuse missing/invalid evidence."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drift-json", required=True, type=Path)
    parser.add_argument("--alert-receipt", required=True,
                        help="local screenshot filename, channel timestamp, or confirmed receipt description")
    parser.add_argument("--dashboard-screenshot", required=True)
    args = parser.parse_args()
    drift = json.loads(args.drift_json.read_text())
    injection = json.loads(Path("reports/injection.json").read_text())
    if drift.get("source") != "Azure managed endpoint console logs":
        raise ValueError("use actual scheduled-cloud output, not a local rehearsal")
    if drift.get("status") != "drift" or not (drift.get("alert") or {}).get("accepted"):
        raise ValueError("cloud check did not capture a delivered alert")
    if injection["rows_sent"] != injection["rows_planned"]:
        raise ValueError("injection replay was incomplete")
    start = datetime.fromisoformat(injection["started_at"])
    detection = datetime.fromisoformat(drift["checked_at"])
    accepted = datetime.fromisoformat(drift["alert_accepted_at"])
    seconds = (accepted - start).total_seconds()
    if seconds < 0 or detection < start:
        raise ValueError("timestamps do not belong to this injection")
    evidence = {"injection_started_at": start.isoformat(), "detected_at": detection.isoformat(),
                "alert_accepted_at": accepted.isoformat(), "detection_to_webhook_seconds": seconds,
                "definition": "first injected request to webhook HTTP acceptance; channel receipt captured separately",
                "alert_receipt": args.alert_receipt, "dashboard_screenshot": args.dashboard_screenshot,
                "threshold": drift["threshold"], "features": drift["features"]}
    Path("reports/injected-drift-evidence.json").write_text(json.dumps(evidence, indent=2),
                                                         encoding="utf-8")
    postmortem = (
        f"What fired: Scheduled PSI detector; threshold {drift['threshold']:.5f}; alert accepted after {seconds:.2f} seconds.\n"
        "True cause: The controlled input replay added 12 C to temp_c; this simulates an upstream calibration error.\n"
        "Retrain, roll back, or no action — and why: Restore the input producer and replay an unshifted window; keep the model, because retraining on corrupted temperatures would learn the error.\n"
        "What this would have cost if unnoticed for a week: Incorrect maintenance decisions and repeated alerts; monetary impact is unmeasured and needs request volume, decision costs, and billing data.\n"
        "How to prevent or detect it faster: Validate sensor calibration and units at ingestion; keep the five-minute schedule and measure Log Analytics ingestion and job startup delay separately.\n"
    )
    Path("reports/postmortem.md").write_text(postmortem, encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    print("Saved measured evidence and the required five-line post-mortem")


if __name__ == "__main__":
    main()
