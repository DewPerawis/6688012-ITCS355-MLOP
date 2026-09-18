"""Lab 2 — prove the registered model can be reloaded by version, from the registry.

    python scripts/reload_check.py --name itcs355-<studentid> --version 3

This is the lab's quiet test. Models that cannot be reloaded six months later are the
commonest form of dead work in industry, and the cause is nearly always a serialization
assumption: a custom class that no longer exists, a library version that moved, a
preprocessing step that only ever lived in a notebook.

Loading from a local file instead of the registry defeats the purpose and is checked.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow

from cloudlayer.factory import get_adapter
from src import config, data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=None, help="registered model name; defaults to cloud.env")
    ap.add_argument("--version", required=True)
    ap.add_argument("--rows", type=int, default=5)
    args = ap.parse_args()

    cfg = config.load(strict=False)
    model_name = args.name or cfg.model_registry_name
    tracking_uri = (
        get_adapter(cfg).tracking_uri()
        if cfg.provider.lower() == "azure"
        else cfg.mlflow_tracking_uri
    )
    mlflow.set_tracking_uri(tracking_uri)

    uri = f"models:/{model_name}/{args.version}"
    print(f"loading {uri}")
    model = mlflow.sklearn.load_model(uri)

    df = data.load_raw(cfg.raw_path)
    _, _, test_df = data.split(df, seed=20260101)
    sample = test_df.head(args.rows)
    preds = model.predict_proba(sample[data.FEATURES])[:, 1]

    if len(preds) != args.rows:
        raise RuntimeError(f"expected {args.rows} predictions, got {len(preds)}")

    for rid, p in zip(sample[data.ID], preds):
        print(f"  reading {rid}: p(failure)={p:.4f}")
    print("\nPASS  model reloaded from the registry and scored rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
