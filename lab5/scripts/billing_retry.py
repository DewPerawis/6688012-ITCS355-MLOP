"""Read-only bounded billing retry, separate from quota and estimate generation."""
import json
from datetime import datetime, timezone

from cloudlayer.planning import BillingThrottled, billing_observation
from cloudlayer.readiness import LAB, inherited_config
from scripts.preflight import progress


def main():
    cfg, _ = inherited_config()
    path = LAB / "reports" / "billing-review.json"
    prior = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report = {"queried_at": datetime.now(timezone.utc).isoformat(), "scope": "read-only billing"}
    for key, filtered in (("group_billing", False), ("lab5_billing", True)):
        cached = prior.get(key, {})
        if cached.get("status") == "ok" and cached.get("queried_at"):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached["queried_at"])).total_seconds()
            if 0 <= age < 86400:
                progress("Reuse successful billing observation under 24h old: " + key)
                report[key] = cached
                continue
        progress("Read " + key)
        try:
            report[key] = billing_observation(cfg, lab5_only=filtered, progress=progress)
        except BillingThrottled as exc:
            report[key] = {"status": "throttled", "http_status": 429, "actual_cost": None,
                           "retry_after_seconds": exc.retry_after_seconds,
                           "retry_headers": exc.retry_headers}
            # Avoid another query against the same throttled service.
            if key == "group_billing":
                report["lab5_billing"] = {"status": "skipped_due_to_throttling", "actual_cost": None}
            break
        except Exception as exc:
            report[key] = {"status": "unavailable", "error_type": type(exc).__name__,
                           "http_status": getattr(exc, "code", None), "actual_cost": None}
    if path.exists():
        history = path.parent / "billing-history"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (history / f"billing-{stamp}.json").write_bytes(path.read_bytes())
    report["note"] = "Full-term THB budget and final Lab 5 actual cost remain unverified. No resources were started."
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {key: {field: value for field, value in body.items() if field in (
        "status", "posted_totals_by_currency", "retry_after_seconds", "http_status", "error_type"
    )} for key, body in report.items() if isinstance(body, dict)}
    print(json.dumps(summary, indent=2), flush=True)
    print(report["note"], flush=True)


if __name__ == "__main__":
    main()
