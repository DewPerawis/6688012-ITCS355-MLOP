"""Delete only the tagged Lab 3 green deployment after traffic rollback."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    cfg = config.load()
    deleted = get_adapter(cfg).delete_deployment(
        cfg.online_endpoint,
        "green",
        {**cfg.tags(3), "model_version": _canary_version()},
    )
    evidence = {
        "deployment": "green",
        "deleted": deleted,
        "observed_at": datetime.now(UTC).isoformat(),
    }
    path = Path("reports/lab3-canary-cleanup.json")
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))
    return 0


def _canary_version() -> str:
    path = Path("reports/lab3-canary-model.json")
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


if __name__ == "__main__":
    raise SystemExit(main())
