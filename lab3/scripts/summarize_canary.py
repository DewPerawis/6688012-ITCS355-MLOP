"""Print a compact canary, detection, rollback, and cleanup summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read(name: str) -> Any:
    return json.loads((Path("reports") / name).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-exit", type=int, required=True)
    args = parser.parse_args()
    model = _read("lab3-canary-model.json")
    deployment = _read("lab3-deployment-green.json")
    probe = _read("lab3-canary-probe.json")
    traffic = _read("lab3-traffic.json")
    cleanup = _read("lab3-canary-cleanup.json")
    latest_canary = next(
        item for item in reversed(traffic) if item["traffic"] == {"blue": 90, "green": 10}
    )
    latest_rollback = next(
        item for item in reversed(traffic) if item["traffic"] == {"blue": 100, "green": 0}
    )
    print("CANARY SUMMARY")
    print(f"version={model['version']} expected_drop={model['expected_absolute_drop']}")
    print(f"green_instance={deployment['instance']}")
    print(f"traffic_90_10_at={latest_canary['observed_at']}")
    print(f"sample_counts={json.dumps(probe['sample_counts'], sort_keys=True)}")
    print(f"detection={json.dumps(probe['detection'], sort_keys=True)}")
    print(f"probe_exit={args.probe_exit}")
    print(f"rollback_100_0_at={latest_rollback['observed_at']}")
    print(f"green_deleted={cleanup['deleted']} at={cleanup['observed_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
