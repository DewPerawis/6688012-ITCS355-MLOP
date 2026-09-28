"""Create or update one versioned Azure ML online deployment."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--instance", default=None)
    parser.add_argument("--out", type=Path, default=Path("reports/lab3-deployment.json"))
    args = parser.parse_args()
    cfg = config.load()
    version = args.model_version or cfg.model_version
    endpoint = args.endpoint or cfg.online_endpoint
    instance = args.instance or cfg.serving_instance
    scoring_uri = get_adapter(cfg).deploy(
        f"{cfg.model_registry_name}:{version}", endpoint, instance
    )
    evidence = {
        "endpoint": endpoint,
        "deployment": cfg.deployment_name,
        "model_name": cfg.model_registry_name,
        "model_version": version,
        "serving_image_digest": cfg.serving_image_uri.split("@", 1)[-1],
        "instance": instance,
        "deployed_at": datetime.now(UTC).isoformat(),
        "scoring_uri_configured": bool(scoring_uri),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
