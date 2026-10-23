"""Part 1: inspect the existing environment/account and save a safe summary.

Run from lab5: python -u -m scripts.preflight
Only reports are written locally. Cloud calls are read-only. No installation or Git mutation.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cloudlayer.readiness import LAB, REPO, inherited_config, inspect_workspace, retail_prices


def progress(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def main():
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": "readiness only; no managed training/deployment/evaluation has run",
              "second_provider": "pending; user currently has Azure only",
              "llm": "not yet verified", "billing": "not queried; reconciliation pending"}
    started = time.monotonic()
    try:
        progress("1/4 Check WSL, Python, tools and existing source")
        is_wsl = platform.system() == "Linux" and "microsoft" in platform.release().lower()
        report["local"] = {"wsl": is_wsl, "python": platform.python_version(),
                           "environment": Path(sys.prefix).name}
        if not is_wsl:
            raise RuntimeError("Select the WSL Python kernel, not Windows Python. See START_HERE_TH.md.")
        if sys.version_info < (3, 11):
            raise RuntimeError("Use the existing Python 3.11+ environment from Lab 4.")
        missing = [tool for tool in ("git", "az", "docker") if not shutil.which(tool)]
        if missing:
            raise RuntimeError("Missing tools in this kernel: " + ", ".join(missing))
        versions = {}
        for package in ("azure-ai-ml", "azure-identity", "ipykernel"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        report["packages"] = versions
        missing = [name for name, version in versions.items() if version is None]
        if missing:
            raise RuntimeError("Missing packages: " + ", ".join(missing)
                               + ". Do not install everything again; send this output for the minimal fix.")
        docker = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}/{{.Architecture}}"],
            capture_output=True, text=True, timeout=25, check=False,
        )
        report["docker"] = {"reachable": docker.returncode == 0,
                            "platform": docker.stdout.strip() if docker.returncode == 0 else None}
        if docker.returncode:
            raise RuntimeError("Docker is not reachable. Start Docker Desktop with WSL integration, then rerun.")
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                capture_output=True, text=True, timeout=15, check=True)
        report["base_commit"] = commit.stdout.strip()
        sources = (
            "lab2/reports/lab2-registry.json", "lab2/reports/lab2-comparison.md",
            "lab4/reports/image-push.json", "lab4/reports/final-cloud-check.json",
            "lab1/course/labs/lab-05-cloud-mlops-and-cost.md",
        )
        report["source_sha256"] = {}
        for relative in sources:
            path = REPO / relative
            if not path.is_file():
                raise RuntimeError("Required previous-lab source missing: " + relative)
            report["source_sha256"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        progress("2/4 Read identifier-only config from previous Labs")
        cfg, sources = inherited_config()
        report["config_sources"] = sources
        report["config"] = {key: value for key, value in cfg.items() if key != "AZURE_SUBSCRIPTION_ID"}
        progress("3/4 Inspect Azure workspace/model, compute, endpoints, schedules and quota")
        inspect_workspace(cfg, progress, report)
        progress("4/4 Read current public DS2 v2 retail price meters")
        try:
            report["prices"] = retail_prices(report["workspace"]["location"])
            report["prices"]["status"] = "ok" if report["prices"]["meters"] else "no_matching_meters"
        except Exception as exc:
            report["prices"] = {"status": "unavailable", "error_type": type(exc).__name__}
        report["status"] = "ready_for_planning"
    except Exception as exc:
        report["status"] = "needs_fix"
        # Persist our actionable messages only; do not persist arbitrary SDK error bodies.
        report["error_type"] = type(exc).__name__
        safe_message = str(exc) if type(exc) in (RuntimeError, ValueError) else (
            "Azure/SDK check failed. Verify az login and subscription access; send the summary below."
        )
        report["message"] = safe_message
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["next"] = "Stop here and send the printed summary; no billable resources have been started."
    reports = LAB / "reports"
    reports.mkdir(exist_ok=True)
    output = reports / "preflight.json"
    if output.exists():
        # Preserve every user-run observation; the latest canonical report stays easy to find.
        history = reports / "preflight-history"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copy2(output, history / f"preflight-{stamp}.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    # Short output for sharing. No account/subscription/tenant IDs, tokens or raw env content.
    summary = {key: report[key] for key in (
        "status", "local", "packages", "docker", "workspace", "incumbent", "error_type", "message"
    ) if key in report}
    summary["inspections"] = {
        key: {"status": report[key]["status"],
              "count": len(report[key].get("items", [])),
              "error_type": report[key].get("error_type")}
        for key in ("compute", "endpoints", "schedules", "quota", "resource_inventory") if key in report
    }
    if "prices" in report:
        prices = report["prices"]
        summary["prices"] = {"status": prices["status"], "meter_count": len(prices.get("meters", []))}
    summary["pending"] = ["Review quota, identities and prices before deploying",
                           "Commit a reviewed estimate before Task 1",
                           "Second provider and LLM access remain separate future requirements",
                           "Billing and term budget are not yet reconciled"]
    summary["report"] = "lab5/reports/preflight.json"
    print("\n--- SEND THIS SUMMARY ---", flush=True)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    print(report["next"], flush=True)
    return 0 if report["status"] == "ready_for_planning" else 1


if __name__ == "__main__":
    sys.exit(main())
