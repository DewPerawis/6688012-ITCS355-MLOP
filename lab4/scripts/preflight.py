"""Read-only local checks that are safe to run first after waking up."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    def installed(name):
        try:
            return importlib.util.find_spec(name) is not None
        except ModuleNotFoundError:
            return False

    checks = {f"python_module_{name}": installed(name)
              for name in ("numpy", "pandas", "sklearn", "fastapi", "mlflow", "pytest", "ruff", "azure.ai.ml")}
    docker = os.getenv("DOCKER", "docker")
    for tool in (docker, "az", "gh", "git"):
        checks[f"tool_{tool}"] = shutil.which(tool) is not None
    if checks[f"tool_{docker}"]:
        result = subprocess.run([docker, "version", "--format", "{{.Server.Version}}"],
                                capture_output=True, text=True)
        checks["docker_engine_running"] = result.returncode == 0
    for label, path in (("hashed_lock", "requirements.txt"), ("local_config", "cloud.env"),
                         ("reference", "data/reference.csv"),
                         ("calibration", "reports/threshold-calibration.json")):
        checks[label] = Path(path).is_file()
    result = {"checked_at": datetime.now(UTC).isoformat(), "python": sys.version.split()[0],
              "checks": checks, "passed": all(checks.values()),
              "note": "read-only local check; no install, commit, push or cloud deployment"}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/preflight.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
