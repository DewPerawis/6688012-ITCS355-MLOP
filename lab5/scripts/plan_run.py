"""Part 2: repair quota inspection and prepare a reviewable pre-run estimate.

Read-only cloud calls. No commit, role grant, resource creation or training.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cloudlayer.planning import billing_observation, inspect_identities, inspect_quota
from cloudlayer.readiness import LAB, inherited_config
from scripts.preflight import progress


def select_linux_meter(prices, sku="Standard_DS2_v2"):
    candidates = [meter for meter in prices.get("meters", [])
                  if meter.get("type") == "Consumption"
                  and meter.get("currencyCode") == "THB"
                  and meter.get("armSkuName") == sku
                  and meter.get("armRegionName") == prices.get("region")
                  and meter.get("unitOfMeasure") == "1 Hour"
                  and meter.get("tierMinimumUnits") == 0
                  and "windows" not in meter.get("productName", "").lower()
                  and not any(word in (meter.get("meterName", "") + " " + meter.get("skuName", "")).lower()
                              for word in ("spot", "low priority"))]
    if len(candidates) != 1 or not isinstance(candidates[0].get("retailPrice"), (float, int)):
        raise ValueError("Expected exactly one Linux on-demand meter. Review prices before estimating.")
    if candidates[0]["retailPrice"] <= 0:
        raise ValueError("Retail rate must be positive")
    return candidates[0]


def estimate_text(preflight, cfg):
    prices = preflight["prices"]
    if prices["region"] != cfg["REGION"]:
        raise ValueError("Preflight pricing region differs from current configuration")
    observed = datetime.fromisoformat(prices["retrieved_at"])
    age_hours = (datetime.now(timezone.utc) - observed).total_seconds() / 3600
    if age_hours < 0 or age_hours > 24:
        raise ValueError("Price observation is over 24h old or in the future; refresh prices before estimating.")
    meter = select_linux_meter(prices)
    rate = meter["retailPrice"]
    compute = 2 * rate
    base = compute + 6
    envelope = (base + 20) * 1.2
    created = datetime.now(timezone.utc).isoformat()
    return f"""# Lab 5 — Pre-run estimate (review before committing)

Prepared: {created}. Student: 6688012. Azure region: {cfg['REGION']}.
This is a proposed short demonstration plan, not measured runtime or actual billing.
No Lab 5 pipeline has been submitted by these preparation tools.

## Price evidence and assumptions

- Source: {prices['source']}
- Retrieved: {prices['retrieved_at']}; meter ID: `{meter['meterId']}`.
- Linux on-demand `{meter['armSkuName']}`: **{rate:.4f} THB/hour**.
- Retail VM reference only; ML service overhead, disks and invoice discounts can differ.
- Dedicated compute is the conservative estimate. Discounted compute must be checked against
  quota/eligibility before use; no discount or Spot availability is assumed here.
- Training cluster: proposed min=0/max=1; at most one active staging instance.
- Planned billable envelope: training 0.5 instance-hour, validation/evaluation/pipeline
  startup/idle allowance 0.5 instance-hour, staging 1 instance-hour. These are planning
  assumptions covering the demonstration attempts, not measurements or enforced timeouts.
- A schedule must be disabled promptly after evidence capture. Additional runs, longer
  provisioning or another VM size require a revised estimate before starting.

## Breakdown

| Component | Planning basis | Estimate / allowance (THB) |
|---|---|---:|
| Training | 0.5 h × {rate:.4f} | {rate * .5:.4f} |
| Pipeline / validation / idle | 0.5 h × {rate:.4f}; compute allocation, not a separate pipeline tariff | {rate * .5:.4f} |
| Serving | 1 h × {rate:.4f} | {rate:.4f} |
| Storage | provisional allowance, no verified usage/tariff calculation yet | 2.0000 |
| Monitoring | provisional allowance for short demonstration | 2.0000 |
| Shared registry/other | provisional allocation; avoid counting the entire shared bill twice | 2.0000 |
| Part A subtotal | compute {compute:.4f} + provisional noncompute 6 | {base:.4f} |
| LLM | provisional budget reserve; model/rates/access not yet selected | 10.0000 |
| Second provider | provisional budget reserve; account/service not yet available | 10.0000 |
| Contingency | 20% of the preceding planning subtotal | {(base + 20) * .2:.4f} |
| Proposed Lab 5 planning envelope | not a billing cap or a forecast accuracy guarantee | **{envelope:.4f}** |

The three noncompute allowances and two future-service reserves are explicit proposals,
not provider quotations or evidence those tasks can be completed at these amounts.
Review/reprice them before using the relevant services. Earlier-lab/shared costs still
consume the course's <800 THB term budget; available headroom has not yet been verified.
The baseline Part A subtotal and reserves must remain separate during reconciliation;
report deviations honestly rather than selecting a subtotal to force a 20% match.

## Pre-run ordering

The user must review and commit this estimate before Task 1. Record that commit SHA in
the later managed-job submission evidence. This preparation step never commits or pushes.
If the scope or assumptions change, preserve the original and commit a dated revision
before executing the changed scope.
""", {"hourly_thb": rate, "part_a_subtotal_thb": round(base, 4),
       "proposed_envelope_thb": round(envelope, 4), "meter_id": meter["meterId"]}


def main():
    reports = LAB / "reports"
    preflight_path = reports / "preflight.json"
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "scope": "read-only planning"}
    try:
        previous = json.loads(preflight_path.read_text(encoding="utf-8"))
        if previous.get("status") != "ready_for_planning":
            raise ValueError("A successful Part 1 report is required")
        report["preflight_sha256"] = hashlib.sha256(preflight_path.read_bytes()).hexdigest()
        cfg, _ = inherited_config()
        for key in ("AZURE_RESOURCE_GROUP", "AZUREML_WORKSPACE", "MODEL_REGISTRY_NAME", "MODEL_VERSION", "REGION"):
            if cfg[key] != previous["config"].get(key):
                raise ValueError("Configuration changed since Part 1: " + key)
        progress("1/4 Recheck quota using the corrected SDK response parser")
        try:
            report["quota"] = inspect_quota(cfg)
        except Exception as exc:
            report["quota"] = {"status": "unavailable", "error_type": type(exc).__name__}
        progress("2/4 Read existing managed identities; no permission changes")
        try:
            report["identities"] = {"status": "ok", "items": inspect_identities(cfg)}
        except Exception as exc:
            report["identities"] = {"status": "unavailable", "error_type": type(exc).__name__}
        progress("3/4 Query posted billing for the course resource group and Lab 5 tags")
        for key, lab5_only in (("group_billing", False), ("lab5_billing", True)):
            try:
                report[key] = billing_observation(cfg, lab5_only=lab5_only)
            except Exception as exc:
                report[key] = {"status": "unavailable", "error_type": type(exc).__name__,
                               "http_status": getattr(exc, "code", None), "actual_cost": None}
        progress("4/4 Prepare the pre-run estimate and cost-report sections")
        text, numbers = estimate_text(previous, cfg)
        target = reports / "lab5-estimate.md"
        # Never overwrite a previously reviewed/committed estimate on a rerun.
        if target.exists():
            report["estimate"] = {"status": "existing_preserved", "path": target.name,
                                  "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        else:
            with target.open("x", encoding="utf-8") as stream:
                stream.write(text)
            report["estimate"] = {"status": "draft_created", "path": target.name, **numbers,
                                  "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        cost = reports / "lab5-cost.md"
        if not cost.exists():
            with cost.open("x", encoding="utf-8") as stream:
                stream.write(COST_TEMPLATE)
        report["status"] = "ready_for_review" if report["quota"]["status"] == "ok" else "needs_quota_fix"
    except Exception as exc:
        report["status"] = "needs_fix"
        report["error_type"] = type(exc).__name__
        report["message"] = str(exc) if type(exc) is ValueError else "Planning failed; send this summary."
    reports.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = reports / "planning.json"
    if path.exists():
        history = reports / "planning-history"
        history.mkdir(exist_ok=True)
        (history / f"planning-{stamp}.json").write_bytes(path.read_bytes())
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    quota = report.get("quota", {})
    summary = {key: report[key] for key in ("status", "error_type", "message", "estimate") if key in report}
    summary["quota"] = {key: quota[key] for key in ("status", "relevant", "error_type") if key in quota}
    summary["identities"] = {"status": report.get("identities", {}).get("status"),
                             "names": [item["name"] for item in report.get("identities", {}).get("items", [])]}
    summary["billing"] = {key: {k: report.get(key, {}).get(k) for k in
                                   ("status", "posted_totals_by_currency", "http_status", "error_type")}
                          for key in ("group_billing", "lab5_billing")}
    print("\n--- SEND THIS SUMMARY ---", flush=True)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    print("Stop here: review quota/billing/estimate before any commit or managed pipeline.", flush=True)
    return 0 if report["status"] == "ready_for_review" else 1


COST_TEMPLATE = """# Lab 5 — Cost report (execution and reconciliation pending)

## 1. Estimate before running

See [lab5-estimate.md](lab5-estimate.md) for price evidence and explicit assumptions.
Pre-run commit SHA: pending user review/commit. No Task 1 execution is recorded yet.

## 2. Actual billing

See `planning.json` for the pre-run RG observation and Lab 5 tag-filtered observation.
These are posted observations, not final Lab 5 consumption. Empty rows are not proof of zero cost.
Final tagged billing, +24h teardown check, FX source and <800 THB full-term reconciliation: pending.

## 3. Estimate versus actual gap

Pending actual charges. Report absolute and percentage differences, scope and exclusions.
Do not treat billing lag or a credit-funded subscription as free usage.

## 4. Component breakdown

Training, storage, serving, pipeline and monitoring: estimate in the linked pre-run report;
measured durations, usage and allocated actual charges pending. Avoid shared-cost double counting.

## 5. Cost per 1,000 predictions

Pending measured sustainable capacity and serving hourly cost.
Formula: hourly cost / (measured predictions per hour at full utilisation × utilisation) × 1,000.

| Utilisation assumption | THB / 1,000 predictions |
|---|---|
| 5% | pending measurements |
| 25% | pending measurements |
| 80% | pending measurements |

## 6. Applied optimisation

Pending measured before/after under the same workload. No optimisation result claimed yet.

## 7. LLM token bill and budget defence

Pending provider/model access, real usage fields and current rates; no word-count token estimates.
Record measured baseline/capped runs and eval gate, cache economics versus observed hits,
and a short nontechnical budget defence after obtaining the measurements.
"""


if __name__ == "__main__":
    sys.exit(main())
