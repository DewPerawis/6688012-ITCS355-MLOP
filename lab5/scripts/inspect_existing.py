"""Inspect the existing Part 5 job once. Never create/update/submit/cancel resources."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from cloudlayer.execute import job_status, endpoint_exists
from cloudlayer.readiness import LAB, inherited_config
from scripts.preflight import progress


def safe_text(text):
    text = re.sub(r"(?i)Bearer\s+\S+", "Bearer <redacted>", text)
    text = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?<query-redacted>", text)
    return text


def error_summary(job):
    error = getattr(job, "error", None)
    if not error:
        return None
    if isinstance(error, dict):
        code, message = error.get("code"), error.get("message")
    else:
        code, message = getattr(error, "code", None), getattr(error, "message", None)
    return {"code": str(code) if code else None, "message": safe_text(str(message or error))[:4000]}


def main():
    from azure.ai.ml import MLClient
    from azure.identity import AzureCliCredential

    state = json.loads((LAB / "reports/managed-execution.json").read_text())
    cfg, _ = inherited_config()
    runtime = state["runtime"]
    for key, name in (("AZURE_SUBSCRIPTION_ID", "subscription"), ("AZURE_RESOURCE_GROUP", "group"),
                      ("AZUREML_WORKSPACE", "workspace")):
        if cfg[key].lower() != runtime[name].lower():
            raise ValueError("Current config does not match the existing job workspace")
    client = MLClient(AzureCliCredential(subscription=cfg["AZURE_SUBSCRIPTION_ID"]),
                      cfg["AZURE_SUBSCRIPTION_ID"], cfg["AZURE_RESOURCE_GROUP"], cfg["AZUREML_WORKSPACE"],
                      enable_telemetry=False, connection_timeout=20, read_timeout=60, retry_total=1)
    variant = state.get("active_normal_variant") or ("normal" if state["jobs"].get("normal") else "degraded")
    name = state["jobs"][variant]["name"]
    progress("Read existing job and child statuses once: " + name)
    parent = client.jobs.get(name)
    children = list(client.jobs.list(parent_job_name=name))
    report = {"inspected_at": datetime.now(timezone.utc).isoformat(), "job": name, "variant": variant,
              "status": job_status(parent.status), "parent_error": error_summary(parent),
              "source_commit": state["jobs"][variant].get("source_commit", state["source_commit"]), "children": [],
              "jobs_submitted": False, "training_started": False, "setup_repeated": False}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for child in children:
        entry = {"name": child.name, "step": child.display_name, "status": job_status(child.status)}
        if entry["status"] == "Failed":
            progress("Read failed child: " + str(child.display_name))
            detail = client.jobs.get(child.name)
            entry["error"] = error_summary(detail)
            target = LAB / "reports" / "job-diagnostics" / stamp / child.name
            try:
                progress("Download existing logs only (no models/data): " + child.name)
                client.jobs.download(name=child.name, download_path=str(target), all=False)
                excerpts = []
                log_names = ("std_log.txt", "stderr.txt", "stdout.txt", "70_driver_log.txt",
                             "stderrlogs.txt", "stdoutlogs.txt", "execution-wrapper.log",
                             "executionlogs.txt")
                paths = sorted((path for path in target.rglob("*")
                                if path.is_file() and path.name in log_names),
                               key=lambda path: (log_names.index(path.name), path.as_posix()))
                # Prefer user errors; include system logs if training never produced a user log.
                for path in paths[:3]:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    excerpts.append({"file": path.relative_to(target).as_posix(),
                                     "tail": safe_text("\n".join(text.splitlines()[-65:]))[-10000:]})
                entry["user_log_excerpts"] = excerpts
            except Exception as exc:
                entry["log_download"] = {"status": "unavailable", "error_type": type(exc).__name__,
                                         "message": safe_text(str(exc))[:1500]}
        report["children"].append(entry)
    progress("Read registry versions, endpoint and current compute nodes; no changes")
    versions = sorted(str(model.version) for model in client.models.list(name=runtime["model_name"]))
    report["no_registration"] = versions == state["baseline_model_versions"]
    report["endpoint_exists"] = endpoint_exists(client, runtime["endpoint"])
    report["compute_nodes"] = {}
    for compute in ("lab5train", "lab5release"):
        try:
            nodes = list(client.compute.list_nodes(name=compute))
            report["compute_nodes"][compute] = {"count": len(nodes)}
        except Exception as exc:
            report["compute_nodes"][compute] = {"status": "unavailable", "error_type": type(exc).__name__}
    gate_failed = any(child["step"] == "evaluate" and child["status"] == "Failed"
                      for child in report["children"])
    downstream_ran = any(child["step"] in ("register", "deploy_staging")
                         and child["status"] in ("Completed", "Running") for child in report["children"])
    report["gate_failure_candidate"] = (variant == "degraded" and report["status"] == "Failed" and gate_failed
                                        and report["no_registration"] and not report["endpoint_exists"]
                                        and not downstream_ran)
    report["next"] = "Send this diagnostic output. Do not rerun setup or submit a new training job yet."
    path = LAB / "reports/part5-inspection.json"
    if path.exists():
        history = LAB / "reports/inspection-history"
        history.mkdir(exist_ok=True)
        (history / (stamp + ".json")).write_bytes(path.read_bytes())
    path.write_text(json.dumps(report, indent=2) + "\n")
    print("\n--- SEND THIS SUMMARY ---", flush=True)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
