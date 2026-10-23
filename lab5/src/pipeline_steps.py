"""Container step logic. All external paths/lineage arrive as arguments or environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from pathlib import Path

def contract(frame, seed=20260101):
    import numpy as np
    from src import data

    if set(frame.columns) != set(data.SCHEMA):
        raise ValueError("data contract: unexpected or missing columns")
    if frame.empty or frame.isna().any().any() or frame[data.ID].duplicated().any():
        raise ValueError("data contract: empty, missing values or duplicate reading IDs")
    for key, dtype in data.SCHEMA.items():
        if str(frame[key].dtype) != dtype:
            raise ValueError("data contract: dtype mismatch for " + key)
    if not set(frame[data.TARGET].unique()) <= {0, 1}:
        raise ValueError("data contract: labels must be binary")
    for feature, (low, high) in data.PLAUSIBLE_RANGES.items():
        if not np.isfinite(frame[feature]).all() or not frame[feature].between(low, high).all():
            raise ValueError("data contract: invalid feature " + feature)
    parts = data.split(frame, seed)
    groups = [set(part[data.GROUP]) for part in parts]
    if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("data contract: group leakage")
    if any(part[data.TARGET].nunique() != 2 for part in parts):
        raise ValueError("data contract: each split needs both classes")
    return parts


def decision(candidate, incumbent, floor=0.40, margin=0.002):
    if not all(math.isfinite(value) for value in (candidate, incumbent, floor, margin)):
        raise ValueError("gate: non-finite metric")
    if not all(0 <= value <= 1 for value in (candidate, incumbent, floor)) or margin < 0:
        raise ValueError("gate: invalid PR-AUC or margin")
    return candidate >= floor and candidate - incumbent >= margin


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    from src import data

    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=("ingest", "validate", "train", "evaluate"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sha256")
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--incumbent", type=float, default=0.40004728306048276)
    parser.add_argument("--margin", type=float, default=0.002)
    parser.add_argument("--floor", type=float, default=0.40)
    parser.add_argument("--degraded", type=int, default=0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.step == "ingest":
        raw = args.input.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if not args.sha256 or digest != args.sha256:
            raise ValueError("ingest hash differs from the versioned Lab 2 source")
        shutil.copyfile(args.input, args.out / "sensors.csv")
        write(args.out / "source.json", {"sha256": digest})
    elif args.step == "validate":
        frame = data.load_raw(args.input / "sensors.csv")
        parts = contract(frame, args.seed)
        shutil.copyfile(args.input / "sensors.csv", args.out / "sensors.csv")
        write(args.out / "contract.json", {"passed": True, "split_rows": [len(p) for p in parts],
                                            "seed": args.seed})
    elif args.step == "train":
        import joblib
        import mlflow.sklearn
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import average_precision_score, roc_auc_score

        train, val, test = contract(data.load_raw(args.input / "sensors.csv"), args.seed)
        checkpoint = args.out / "checkpoint.joblib"
        signature = {"data_sha256": hashlib.sha256((args.input / "sensors.csv").read_bytes()).hexdigest(),
                     "seed": args.seed, "depth": 8, "min_leaf": 8, "trees": 240}
        if args.degraded:
            from sklearn.dummy import DummyClassifier

            model = DummyClassifier(strategy="prior")
        elif checkpoint.exists():
            # Checkpoints are loaded only from this run's controlled output directory.
            saved = joblib.load(checkpoint)
            if saved["signature"] != signature:
                raise ValueError("checkpoint lineage/config mismatch")
            model = saved["model"]
        else:
            model = RandomForestClassifier(n_estimators=80, max_depth=8, min_samples_leaf=8,
                                           random_state=args.seed, n_jobs=-1, warm_start=True)
            model.fit(train[data.FEATURES], train[data.TARGET])
            joblib.dump({"signature": signature, "model": model}, checkpoint)
        if not args.degraded:
            model.set_params(n_estimators=240)
        model.fit(train[data.FEATURES], train[data.TARGET])
        metrics = {"seed": args.seed, "signature": signature,
                   "deliberate_degradation": bool(args.degraded),
                   "training_job_id": os.environ.get("LAB5_TRAINING_JOB_ID"),
                   "git_commit": os.environ.get("LAB5_GIT_COMMIT"),
                   "data_version": os.environ.get("LAB5_DATA_VERSION"),
                   "image_digest": os.environ.get("LAB5_IMAGE_DIGEST")}
        for name, part in (("val", val), ("test", test)):
            prediction = model.predict_proba(part[data.FEATURES])[:, 1]
            metrics[name + "_pr_auc"] = float(average_precision_score(part[data.TARGET], prediction))
            metrics[name + "_roc_auc"] = float(roc_auc_score(part[data.TARGET], prediction))
        mlflow.sklearn.save_model(model, str(args.out / "model"))
        if os.environ.get("MLFLOW_TRACKING_URI"):
            import mlflow

            with mlflow.start_run(run_id=os.environ.get("MLFLOW_RUN_ID"), run_name="lab5-training") as run:
                metrics["mlflow_run_id"] = run.info.run_id
                mlflow.log_metrics({key: value for key, value in metrics.items()
                                    if key.startswith(("val_", "test_"))})
                mlflow.log_params({"seed": args.seed,
                                   "model_type": type(model).__name__,
                                   "deliberate_degradation": bool(args.degraded)})
                mlflow.set_tags({key: str(metrics[key]) for key in
                                 ("git_commit", "data_version", "image_digest", "training_job_id")})
        write(args.out / "metrics.json", metrics)
        print(json.dumps(metrics), flush=True)
    else:
        metrics = json.loads((args.input / "metrics.json").read_text())
        observed = float(metrics["val_pr_auc"])
        candidate = observed
        report = {"passed": decision(candidate, args.incumbent, args.floor, args.margin),
                  "measured_val_pr_auc": observed, "evaluated_val_pr_auc": candidate,
                  "deliberate_degradation": bool(metrics.get("deliberate_degradation")), "incumbent": args.incumbent,
                  "floor": args.floor, "margin": args.margin,
                  "note": "Operational guard only; this single-seed delta does not prove a stable gain."}
        write(args.out / "gate.json", report)
        print(json.dumps(report), flush=True)
        if not report["passed"]:
            raise SystemExit("GATE FAIL: registration and deployment must not run")


if __name__ == "__main__":
    main()
