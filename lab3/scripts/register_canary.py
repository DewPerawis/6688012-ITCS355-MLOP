"""Register a verified, slightly weaker Lab 2 run as a separate canary model version."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config

# This run is present in the committed Lab 2 comparison. Its validation PR-AUC is
# 0.389062 versus 0.400047 for production: a measured 0.010985 absolute decrease.
DEFAULT_CANARY_RUN = "49fd25d0-0b36-4958-ae0f-905190a2bb25"
DEFAULT_CANARY_METRIC = 0.389062


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_CANARY_RUN)
    parser.add_argument("--production-version", default="1")
    parser.add_argument("--min-drop", type=float, default=0.005)
    parser.add_argument("--max-drop", type=float, default=0.030)
    parser.add_argument("--out", type=Path, default=Path("reports/lab3-canary-model.json"))
    args = parser.parse_args()

    cfg = config.load()
    adapter = get_adapter(cfg)
    production_tags = adapter.get_model_tags(
        cfg.model_registry_name, args.production_version
    )
    production_metric = float(production_tags["metric_val"])
    canary_metric = DEFAULT_CANARY_METRIC
    degradation = production_metric - canary_metric
    if not args.min_drop <= degradation <= args.max_drop:
        raise RuntimeError(
            f"candidate degradation {degradation:.6f} is outside "
            f"[{args.min_drop:.6f}, {args.max_drop:.6f}]"
        )

    tags = {
        "lab3_role": "canary",
        "production_reference_version": args.production_version,
        "metric_name": "val_pr_auc",
        "production_metric": f"{production_metric:.9f}",
        "canary_metric": f"{canary_metric:.9f}",
        "expected_absolute_drop": f"{degradation:.9f}",
        "source_run_id": args.run_id,
    }
    version = adapter.register_model(
        f"runs:/{args.run_id}/model", cfg.model_registry_name, tags
    )
    evidence = {
        "name": cfg.model_registry_name,
        "version": version,
        "registered_at": datetime.now(UTC).isoformat(),
        **tags,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
