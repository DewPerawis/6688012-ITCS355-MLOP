"""One user-run batch: offline checks, read-only inventory, fresh billing and one report.

Never creates compute, trains, deploys, changes roles, deletes resources or changes Git.
External demonstrations and the 24-hour wait are reported honestly, not simulated.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cloudlayer.planning import BillingThrottled, billing_observation
from cloudlayer.readiness import LAB, inherited_config, model_summary
from scripts.preflight import progress


def attempt(action):
    try:
        return {"status": "ok", "result": action()}
    except Exception as exc:
        return {"status": "unavailable", "error_type": type(exc).__name__}


def main():
    from azure.ai.ml import MLClient
    from azure.identity import AzureCliCredential

    now = datetime.now(timezone.utc)
    state = json.loads((LAB / "reports/managed-execution.json").read_text())
    cleanup = json.loads((LAB / "reports/cleanup-runtime.json").read_text())
    cfg, _ = inherited_config()
    runtime = state["runtime"]
    for key, field in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                       ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != runtime[field].lower():
            raise ValueError("Workspace configuration differs from recorded evidence")
    due = datetime.fromisoformat(cleanup["finished_at"]) + timedelta(hours=24)
    report = {"checked_at": now.isoformat(), "submission_ready": False,
              "scope": "batch verification and reporting only", "cloud_mutations": False,
              "recorded_cleanup": cleanup["status"], "billing_24h_due": due.isoformat(),
              "billing_24h_elapsed": now >= due, "billing": {}}
    progress("1/5 Run existing offline checks and provider-string audit")
    test = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                          cwd=LAB, capture_output=True, text=True, timeout=120)
    print(test.stdout, end="", flush=True)
    print(test.stderr, end="", flush=True)
    report["offline_tests"] = {"passed": test.returncode == 0, "exit_code": test.returncode}
    pattern = re.compile(r"azure|aws|gcp|boto|sagemaker|vertex|google\.cloud", re.I)
    report["provider_audit_hits"] = [path.relative_to(LAB).as_posix() for path in (LAB / "src").glob("*.py")
                                     if pattern.search(path.read_text())]
    progress("2/5 Read remaining endpoint/compute/schedule names and retained model v3")
    client = MLClient(AzureCliCredential(subscription=runtime["subscription"]), runtime["subscription"],
                      runtime["group"], runtime["workspace"], enable_telemetry=False,
                      connection_timeout=20, read_timeout=60, retry_total=1)
    def tagged(resource):
        return all((resource.tags or {}).get(key) == value
                   for key, value in {"course": "itcs355", "student": "6688012", "lab": "5"}.items())
    report["inventory"] = {
        "endpoints": attempt(lambda: [item.name for item in client.online_endpoints.list()
                                       if tagged(item) or item.name == runtime["endpoint"]]),
        "compute": attempt(lambda: [item.name for item in client.compute.list()
                                     if tagged(item) or item.name in ("lab5train", "lab5release")]),
        "schedules": attempt(lambda: [item.name for item in client.schedules.list() if tagged(item)]),
        "model_v3": attempt(lambda: model_summary(client.models.get(runtime["model_name"], "3")))}
    progress("3/5 Query fresh posted billing; do not reuse the pre-execution cache")
    for label, filtered in (("course_group", False), ("lab5_tags", True)):
        try:
            report["billing"][label] = billing_observation(cfg, lab5_only=filtered, progress=progress)
        except BillingThrottled as exc:
            report["billing"][label] = {"status": "throttled", "actual_cost": None,
                                        "retry_after_seconds": exc.retry_after_seconds}
            break
        except Exception as exc:
            report["billing"][label] = {"status": "unavailable", "actual_cost": None,
                                        "error_type": type(exc).__name__}
    progress("4/5 Collect evidence filenames and requirements that remain unmet")
    report["portal_screenshot_candidates"] = [str(path.relative_to(LAB)) for path in (LAB / "reports").rglob("*")
                                               if "job-diagnostics" not in path.parts
                                               and path.suffix.lower() in (".png", ".jpg", ".jpeg")]
    report["screenshot_note"] = "File presence does not verify screenshot contents; manual Portal evidence remains required."
    report["remaining"] = [
        "Task 1: one successful six-step triggered execution (current success uses a separate deployment continuation)",
        "Task 2: deliberate permission removal and observed failure (initial missing Reader is not removal)",
        "Task 3: actual retraining schedule; strategy comparison is documented as a proposal",
        "Task 4: second-provider upload/download/invoke demonstration and measured reflection",
        "Tasks 7-9: student LLM golden cases/baseline/regression/guardrail and real provider token usage",
        "Task 5: final cost allocation, FX, 5/25/80% utilisation, applied optimisation and term budget reconciliation",
        "Task 6: manually verified Portal screenshot and billing observation at least 24 hours after cleanup"]
    progress("5/5 Write one wrap-up report and one commit checklist")
    output = LAB / "reports/final-batch.json"
    if output.exists():
        history = LAB / "reports/inspection-history"
        history.mkdir(exist_ok=True)
        (history / (now.strftime("%Y%m%dT%H%M%S%fZ") + "-final-batch.json")).write_bytes(output.read_bytes())
    output.write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Lab 5 batch review", "", "This is not a completed Lab 5 submission.", "",
             "Recorded success: model v3 deployed and smoke tested; named runtime resources were removed.",
             "Fresh read-only review: " + report["checked_at"], "",
             "## Current checks", "", "```json", json.dumps({key: report[key] for key in
              ("offline_tests", "provider_audit_hits", "inventory", "billing_24h_due", "billing_24h_elapsed")}, indent=2),
             "```", "", "## Fresh posted billing", "", "```json",
             json.dumps(report["billing"], indent=2), "```", "",
             "Empty billing rows are not zero cost. Shared Storage/ACR remain; FX and full-term accounting are unverified.",
             "", "## Outstanding requirements", ""]
    lines += ["- " + value for value in report["remaining"]]
    lines += ["", "## One commit after reviewing this batch", "",
              "Include changed source/notebooks and reports under lab5 only. Exclude credentials, raw logs and local snapshots.",
              "Suggested message: `docs: consolidate Lab 5 recovery cleanup and billing evidence`", "",
              "The notebook performs no Git staging/commit/push. Keep the original failed parent status unchanged."]
    (LAB / "reports/final-batch.md").write_text("\n".join(lines) + "\n")
    print("\n--- SEND THIS SUMMARY ---", flush=True)
    print(json.dumps({key: report[key] for key in ("submission_ready", "offline_tests", "provider_audit_hits",
                     "inventory", "billing_24h_due", "billing_24h_elapsed", "cloud_mutations")}, indent=2), flush=True)
    print("Reports: lab5/reports/final-batch.md and final-batch.json. Send this output once; no resource was started.", flush=True)


if __name__ == "__main__":
    main()
