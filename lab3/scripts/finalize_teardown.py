"""Delete the exact Lab 3 endpoint and record verified teardown evidence."""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def update_reports(endpoint: str, deleted_at: str, verified_at: str) -> None:
    report_path = Path("reports/lab3-load.md")
    report = report_path.read_text(encoding="utf-8")
    heading = "## Teardown\n"
    if heading not in report:
        raise RuntimeError("teardown section missing from reports/lab3-load.md")
    report = report.split(heading, 1)[0] + heading + f"""
- Canary deployment `green`: deleted at `2026-09-28T01:02:10.766741+00:00`
- Production endpoint `{endpoint}`: deletion completed at `{deleted_at}`
- Azure SDK absence verification completed at `{verified_at}`
- Azure Portal visual confirmation: perform once before submission; it is not claimed by this automated check
- Settled Cost Management check: review later because Azure billing data can lag
"""
    report_path.write_text(report, encoding="utf-8")

    readme_path = Path("README.md")
    readme = readme_path.read_text(encoding="utf-8")
    old = (
        "analysis are stored under `reports/`; the production endpoint remains active only until the\n"
        "final evidence commit is created, after which it must be deleted to stop compute charges."
    )
    new = (
        "analysis are stored under `reports/`. The production endpoint and canary deployment were\n"
        "deleted after evidence capture, and the automated absence check is recorded in the report."
    )
    if old not in readme:
        raise RuntimeError("expected README evidence-status text was not found")
    readme_path.write_text(readme.replace(old, new), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-endpoint", required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/lab3-teardown.json"))
    args = parser.parse_args()
    cfg = config.load()
    if args.confirm_endpoint != cfg.online_endpoint:
        raise RuntimeError("confirmation does not exactly match ONLINE_ENDPOINT")

    adapter = get_adapter(cfg)
    affected = adapter.teardown(cfg.tags(3))
    deleted_at = utc_now()
    for attempt in range(12):
        if not adapter.endpoint_exists(cfg.online_endpoint):
            break
        if attempt == 11:
            raise RuntimeError("endpoint still exists after deletion wait")
        print(".", end="", flush=True)
        time.sleep(5)
    verified_at = utc_now()
    evidence = {
        "affected": affected,
        "deleted_at": deleted_at,
        "endpoint": cfg.online_endpoint,
        "exists_after_teardown": False,
        "portal_confirmation": "manual check required",
        "verified_absent_at": verified_at,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    update_reports(cfg.online_endpoint, deleted_at, verified_at)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
