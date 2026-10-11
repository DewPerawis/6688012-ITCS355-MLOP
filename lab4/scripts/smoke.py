"""Invoke three known payloads through the adapter and verify the response contract."""
from __future__ import annotations

import argparse

from cloudlayer.factory import get_adapter
from src import config

PAYLOADS = (
    {
        "temp_c": 78.4,
        "vibration_mm_s": 3.1,
        "pressure_kpa": 315.2,
        "hours_since_service": 4200.0,
        "load_pct": 68.0,
        "ambient_humidity": 55.0,
    },
    {
        "temp_c": 92.0,
        "vibration_mm_s": 6.0,
        "pressure_kpa": 300.0,
        "hours_since_service": 8000.0,
        "load_pct": 90.0,
        "ambient_humidity": 70.0,
    },
    {
        "temp_c": 60.0,
        "vibration_mm_s": 1.2,
        "pressure_kpa": 330.0,
        "hours_since_service": 300.0,
        "load_pct": 35.0,
        "ambient_humidity": 45.0,
    },
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", default=None)
    args = parser.parse_args()
    cfg = config.load()
    adapter = get_adapter(cfg)
    for index, payload in enumerate(PAYLOADS, 1):
        response = adapter.invoke(cfg.online_endpoint, payload, deployment=args.deployment)
        probability = float(response["probability"])
        if not 0.0 <= probability <= 1.0:
            raise RuntimeError(f"case {index} returned invalid probability")
        if str(response["model_version"]) != cfg.model_version and args.deployment is None:
            raise RuntimeError(f"case {index} returned unexpected model version")
        print(f"PASS case={index} probability={probability:.6f} version={response['model_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
