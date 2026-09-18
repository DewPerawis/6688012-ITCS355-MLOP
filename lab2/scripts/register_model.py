"""Register the selected run with complete lineage, then promote it to Staging."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow

from cloudlayer.factory import get_adapter
from src import config


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--experiment", default="itcs355-lab2")
    p.add_argument("--run-id", default=None)
    p.add_argument("--name", default=None)
    p.add_argument("--stage", default="Staging")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = config.load()
    adapter = get_adapter(cfg)
    tracking_uri = adapter.tracking_uri() if cfg.provider.lower() == "azure" else cfg.mlflow_tracking_uri
    mlflow.set_tracking_uri(tracking_uri)

    run_id = args.run_id
    if not run_id:
        experiment = mlflow.get_experiment_by_name(args.experiment)
        if experiment is None:
            raise RuntimeError(f"experiment {args.experiment!r} does not exist")
        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string="tags.selected_candidate = 'true'",
        )
        if len(runs) != 1:
            raise RuntimeError(f"expected one selected run, found {len(runs)}")
        run_id = str(runs.iloc[0]["run_id"])

    name = args.name or cfg.model_registry_name
    version = adapter.register_model(f"runs:/{run_id}/model", name)
    adapter.promote_model(name, version, stage=args.stage)
    evidence = {
        "name": name,
        "version": version,
        "stage": args.stage,
        "mlflow_run_id": run_id,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    out = cfg.reports_dir / "lab2-registry.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True))
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
