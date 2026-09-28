"""Print non-secret Lab 3 configuration readiness."""
from __future__ import annotations

import shutil
import subprocess

from src import config


def main() -> int:
    cfg = config.load(strict=False)
    checks = {
        "Azure subscription configured": bool(cfg.azure_subscription_id),
        "resource group configured": bool(cfg.azure_resource_group),
        "workspace configured": bool(cfg.azureml_workspace),
        "registry repository configured": bool(cfg.container_registry),
        "model version exact": cfg.model_version.isdigit(),
        "endpoint name configured": bool(cfg.online_endpoint),
        "Azure CLI present": shutil.which("az") is not None,
        "Docker CLI present": shutil.which("docker") is not None
        or shutil.which("docker.exe") is not None,
    }
    if checks["Azure CLI present"]:
        result = subprocess.run(
            ["az", "account", "show", "--query", "id", "-o", "tsv"],
            capture_output=True,
            text=True,
        )
        checks["Azure CLI authenticated"] = result.returncode == 0 and bool(result.stdout.strip())
    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {label}")
    passed_count = sum(checks.values())
    print(f"{passed_count}/{len(checks)} checks passed")
    return 0 if passed_count == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
