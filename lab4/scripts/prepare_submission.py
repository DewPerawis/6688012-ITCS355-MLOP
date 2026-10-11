"""Assemble local nonsecret evidence and a staging manifest; never commit or push."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def main():
    reports = Path("reports")
    baseline = next((reports / "cloud-jobs/amiable_orange_pl32730vvg").rglob("outputs/drift.json"))
    drift = next((reports / "cloud-jobs/itcs355-6688012-lab4-drift-08584098484054611101308887078CU10").rglob("outputs/drift.json"))
    shutil.copyfile(baseline, reports / "cloud-baseline.json")
    shutil.copyfile(drift, reports / "cloud-drift.json")
    for source, target in (("lab4-deployment.json", "lab4-deployment.json"),
                           ("image-push.json", "image-push.json"),
                           ("registry-container-integration.json", "staging-registry-container-integration.json")):
        shutil.copyfile(reports / "staging-04aedd4" / source, reports / target)
    begin, end = read(reports / "lab4-deployment.json"), read(reports / "lab4-teardown.json")
    pricing = read(reports / "retail-prices.json")
    prices = {item["sku"]: item["candidates"][0]["retailPrice"] for item in pricing["prices"]
              if len(item["candidates"]) == 1}
    start_hours = (datetime.fromisoformat(end["verified_at"]) - datetime.fromisoformat(begin["deployment_started_at"])).total_seconds() / 3600
    completed_hours = (datetime.fromisoformat(end["verified_at"]) - datetime.fromisoformat(begin["deployed_at"])).total_seconds() / 3600
    billing = read(reports / "billing-observation.json")
    columns = [column["name"] for column in billing.get("response", {}).get("properties", {}).get("columns", [])]
    records = [dict(zip(columns, row, strict=True)) for row in billing.get("response", {}).get("properties", {}).get("rows", [])]
    totals = {}
    for record in records:
        currency = record["Currency"]
        totals[currency] = totals.get(currency, 0) + record["PreTaxCost"]
    result = {"status": "partial_retail_reference_not_invoice",
              "serving_price_usd_per_hour": prices["Standard_DS2_v2"],
              "monitor_price_usd_per_hour": prices["Standard_DS1_v2"],
              "serving_elapsed_hours_from_start": start_hours,
              "serving_elapsed_hours_from_completion": completed_hours,
              "serving_reference_cost_usd_from_start": start_hours * prices["Standard_DS2_v2"],
              "serving_reference_cost_usd_from_completion": completed_hours * prices["Standard_DS2_v2"],
              "monitor_billable_hours": None, "actual_lab4_billed_cost": None,
              "posted_resource_group_totals": totals,
              "limitation": "Elapsed-time references are not billing bounds. Monitor VM allocation time is unmeasured. Posted costs include shared earlier-lab resources; latest compute charges are absent."}
    (reports / "cost-estimate.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = """# Lab 4 submission evidence — 6688012

The cloud exercise completed on 12 October 2026, Thailand time. Implementation and evidence
were published in commit `d9b23e8`; final CI run `38183928346` completed successfully with
deployment skipped. The handout's 12 deliverables are mapped below and checked in README.
Cost Management reconciliation must be refreshed after
Azure posts the recent compute usage; the current billing snapshot is not a final Lab 4 bill.

| Requirement | Actual evidence |
|---|---|
| Unit, data, leakage, model and integration tests | 28 local tests passed; real image integration passed in main CI and against registry model version 1 during CD |
| Incident explanations | README names dropped features, wrong units/ranges, missing values, invalid labels, duplicate identifiers and machine leakage |
| CI gates | Main run 38171649219 passed; full CI/CD run 38174583649 subsequently passed |
| Blocked bad commit | PR #1; run 38172414175; test_training_schema_contract; training schema mismatch; image build/deploy skipped; PR closed unmerged |
| SHA image and staging | image-push.json and lab4-deployment.json; model itcs355-6688012:1; serving image tagged 04aedd4 full SHA and pinned by digest |
| Identity federation | Azure login succeeded; immutable GitHub subject; workspace Contributor and ACR AcrPush/Reader at resource scopes |
| Five-signal dashboard | monitoring/workbook.json; workbook-evidence.json; dashboard-cloud-data.json; dashboard-cloud-evidence.png/pdf |
| SLO | monitoring/slo.yaml states target, window and error-budget response; this short exercise does not prove 30-day compliance |
| Baseline | cloud-baseline.json: stable; 500 rows; temp_c PSI 0.01305214; no alert |
| Scheduled drift | scheduled-run.json proves Schedule source and Completed; cloud-drift.json records 500 rows and PSI 1.21851169 versus threshold 0.76223008 |
| Actual alert receipt | Discord HTTP 204; discord-drift-alert.png and discord-drift-alerts.png show actual messages |
| Detection interval | injected-drift-evidence.json: injection to webhook acceptance 521.911988 seconds; detection to HTTP acceptance 7.707207 seconds |
| Post-mortem | postmortem.md has five lines; restore corrupted input producer, keep the registered model, do not retrain on the +12 C error |
| Teardown | lab4-teardown.json and final-cloud-check.json: endpoint, schedule and monitor compute absent |
| Cost observations | retail-prices.json, billing-observation.json, cost-estimate.json and lab4-cost.md; compute bill still pending |

## Dashboard provenance

The dashboard figure is rendered from five actual retained Log Analytics query results.
It is not presented as an Azure Portal screenshot. It shows the observed temperature
mean shift from about 79 C to 91 C, historical model version 1, batch request rate,
observed 4xx/5xx fractions and gateway p50/p95/p99. Only observed bins are plotted.
The exported window also includes the earlier injected replay whose Discord delivery
failed with HTTP 403; the final successful injection is marked separately.
The finalizer identifies dashboard_evidence_kind=data_export.

The Portal workbook was configured during the experiment. For a Portal screenshot,
import monitoring/workbook-evidence.json within its last-24-hour query scope and capture
the five graphs; the endpoint is not needed because logs are retained. The offline PNG/PDF
can be reproduced later from saved dashboard-cloud-data.json without any cloud calls.

## Runtime corrections

CI fixture export was made explicit as cloudpickle. GitHub's immutable subject IDs were
matched in Azure federation. Reader was added on the ACR so the CI identity could discover
the registry in addition to pushing images. Initial log ingestion delayed readiness.
Scheduled delivery initially failed with HTTP 403; the documented Discord User-Agent
and Discord-specific content payload corrected delivery. A channel setup test remains
distinct from actual scheduled drift evidence.

## Publication boundary

submission-files.txt allowlists source and nonsecret measured evidence. It excludes cloud.env,
webhook URL files, raw/generated data, downloaded models and full cloud system/debug logs.
Workspace, Storage, ACR, Key Vault, registry and workbook remain for later coursework.
The three billable Lab 4 compute/schedule resources were removed; residual storage,
registry and log retention charges are not claimed to be zero.
"""
    (reports / "submission-summary.md").write_text(summary, encoding="utf-8")
    sources = [Path("README.md")]
    for folder in ("cloudlayer", "monitoring", "scripts", "tests"):
        sources.extend(path for path in Path(folder).rglob("*") if path.is_file()
                       and "__pycache__" not in path.parts
                       and path.suffix in {".py", ".json", ".kql", ".yaml"})
    evidence = [path for path in reports.iterdir() if path.is_file()
                and path.suffix in {".json", ".md", ".png", ".pdf", ".log"}]
    selected = sorted(set(sources + evidence))
    ignored = subprocess.run(["git", "check-ignore", "--stdin"],
                             input="\n".join(path.as_posix() for path in selected) + "\n",
                             text=True, capture_output=True, check=False)
    if ignored.returncode not in (0, 1):
        raise RuntimeError("could not verify Git ignore policy")
    ignored_paths = set(ignored.stdout.splitlines())
    selected = [path for path in selected if path.as_posix() not in ignored_paths]
    pattern = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|https://(?:discord\.com|discordapp\.com)/api/webhooks/[0-9]+/[A-Za-z0-9_-]+|https://hooks\.slack\.com/services/[A-Za-z0-9/]+|AccountKey=[A-Za-z0-9+/]{40,}")
    for path in selected:
        if path.suffix not in {".png", ".pdf"} and pattern.search(path.read_text(encoding="utf-8")):
            raise RuntimeError(f"possible secret in {path}; no staging manifest created")
    manifest = ["lab4/" + path.as_posix() for path in selected]
    manifest.append("lab4/reports/submission-files.txt")
    (reports / "submission-files.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"Prepared {len(manifest)} allowlisted paths; no high-confidence secret patterns found")
    print("No files staged, committed or pushed")


if __name__ == "__main__":
    main()
