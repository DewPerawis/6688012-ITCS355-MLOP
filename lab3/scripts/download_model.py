"""Download the exact registered version for a local container smoke test."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/model-v1"))
    args = parser.parse_args()
    cfg = config.load()
    adapter = get_adapter(cfg)
    uri = f"azureml:{cfg.model_registry_name}:{cfg.model_version}"
    destination = adapter.download_model(
        cfg.model_registry_name, cfg.model_version, str(args.out)
    )
    result = {"model_uri": uri, "local_path": destination}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
