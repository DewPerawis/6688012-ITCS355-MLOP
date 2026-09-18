"""Budgeted, resumable Lab 2 hyperparameter study.

The primary comparison contains exactly 12 distinct configurations spanning three
behaviour-changing Random Forest hyperparameters. After selecting a cost-efficient
candidate, five additional seed runs quantify split/training variance. Every run logs
validation and held-out test metrics separately, duration, instance and estimated cost.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import mlflow
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from src import config, costs, data, seeds
from src.train import dvc_data_version, git_commit


SEARCH_SPACE: dict[str, list[int]] = {
    "n_estimators": [80, 160, 240],
    "max_depth": [4, 8],
    "min_samples_leaf": [2, 8],
}
SELECTION_METRIC = "val_pr_auc"


def grid(space: dict[str, list[int]]) -> list[dict[str, int]]:
    keys = list(space)
    return [dict(zip(keys, values)) for values in itertools.product(*(space[k] for k in keys))]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITCS355 Lab 2 — budgeted study")
    p.add_argument("--trials", type=int, default=12)
    p.add_argument("--budget-thb", type=float, default=150.0)
    p.add_argument("--instance", default=None, help="exact key in src/costs.py")
    p.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    p.add_argument("--seed-repeats", type=int, default=5)
    p.add_argument("--selection-tolerance", type=float, default=0.005)
    p.add_argument("--max-trial-minutes", type=float, default=10.0)
    p.add_argument("--experiment", default="itcs355-lab2")
    p.add_argument("--data-path", type=Path, default=None)
    p.add_argument("--tracking-uri", default=None)
    p.add_argument("--checkpoint", type=Path, default=Path("reports/tune_checkpoint.json"))
    p.add_argument("--summary-out", type=Path, default=Path("reports/lab2-study.json"))
    p.add_argument(
        "--interrupt-after",
        type=int,
        default=0,
        help="Evidence hook: checkpoint, then fail once after N study trials.",
    )
    return p.parse_args()


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "completed": {}, "spent_thb": 0.0}
    state = json.loads(path.read_text())
    if state.get("schema_version") != 1 or not isinstance(state.get("completed"), dict):
        raise ValueError(f"unsupported or corrupt checkpoint: {path}")
    return state


def save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True))
    temporary.replace(path)


def trial_key(phase: str, params: dict[str, int], seed: int) -> str:
    return json.dumps({"phase": phase, "params": params, "seed": seed}, sort_keys=True)


def select_candidate(
    results: list[dict[str, Any]], tolerance: float
) -> dict[str, Any]:
    """Use a transparent near-best/lowest-cost rule instead of chasing a noisy maximum."""
    best_metric = max(result[SELECTION_METRIC] for result in results)
    eligible = [result for result in results if result[SELECTION_METRIC] >= best_metric - tolerance]
    return min(
        eligible,
        key=lambda result: (
            result["cost_thb"],
            result["params"]["n_estimators"],
            result["params"]["max_depth"],
            result["params"]["min_samples_leaf"],
        ),
    )


def _run_trial(
    *,
    phase: str,
    index: int,
    params: dict[str, int],
    seed: int,
    train_df,
    val_df,
    test_df,
    rate_thb_h: float,
    instance: str,
    provenance: dict[str, str],
) -> dict[str, Any]:
    started = time.perf_counter()
    parent_active = mlflow.active_run() is not None
    with mlflow.start_run(
        run_name=f"{phase}-{index:02d}-seed-{seed}", nested=parent_active
    ) as active_run:
        model = RandomForestClassifier(random_state=seed, n_jobs=-1, **params)
        model.fit(train_df[data.FEATURES], train_df[data.TARGET])

        metrics: dict[str, float] = {}
        for name, part in (("val", val_df), ("test", test_df)):
            probabilities = model.predict_proba(part[data.FEATURES])[:, 1]
            metrics[f"{name}_roc_auc"] = float(
                roc_auc_score(part[data.TARGET], probabilities)
            )
            metrics[f"{name}_pr_auc"] = float(
                average_precision_score(part[data.TARGET], probabilities)
            )

        duration_s = time.perf_counter() - started
        cost_thb = duration_s / 3600.0 * rate_thb_h
        run_id = active_run.info.run_id
        mlflow.log_params({**params, "seed": seed, "instance": instance, "phase": phase})
        mlflow.log_metrics({
            **metrics,
            "duration_s": duration_s,
            "cost_thb": cost_thb,
        })
        mlflow.set_tags({
            **provenance,
            "mlflow_run_id": run_id,
            "lab": "2",
            "phase": phase,
        })
        mlflow.sklearn.log_model(
            model,
            name="model",
            pip_requirements=[
                "scikit-learn==1.8.0",
                "numpy==2.4.4",
                "pandas==2.3.3",
            ],
        )

    return {
        "phase": phase,
        "index": index,
        "run_id": run_id,
        "params": params,
        "seed": seed,
        "instance": instance,
        "duration_s": duration_s,
        "cost_thb": cost_thb,
        **metrics,
    }


def main() -> None:
    args = parse_args()
    if args.trials < 12:
        raise ValueError("Lab 2 requires at least 12 study trials")
    candidates = grid(SEARCH_SPACE)
    if args.trials > len(candidates):
        raise ValueError(f"search space has only {len(candidates)} distinct configurations")
    if args.seed_repeats < 2:
        raise ValueError("seed variance requires at least two seed runs")
    if args.budget_thb <= 0 or args.max_trial_minutes <= 0:
        raise ValueError("budget and max trial duration must be positive")

    cfg = config.load(strict=False)
    instance = args.instance or (
        "local" if cfg.provider.lower() == "local" else cfg.training_instance
    )
    rate_thb_h = costs.hourly_rate(cfg.provider, instance)
    projected_trial_cost = rate_thb_h * args.max_trial_minutes / 60.0

    raw_path = args.data_path or cfg.raw_path
    base_seed = seeds.set_all(args.seed)
    frame = data.load_raw(raw_path)
    fingerprint = data.data_fingerprint(raw_path)
    train_df, val_df, test_df = data.split(frame, seed=base_seed)
    revision = git_commit(cfg.git_commit)
    data_version = os.environ.get("DATA_VERSION") or dvc_data_version(
        cfg.data_dir / "raw.dvc"
    )
    provenance = {
        "git_commit": revision,
        "data_version": data_version,
        "data_fingerprint": fingerprint,
        "training_job_id": os.environ.get("TRAINING_JOB_ID", "local"),
        "image_digest": os.environ.get("IMAGE_DIGEST", "local"),
        "split_strategy": "group_by_machine_id",
    }

    mlflow.set_tracking_uri(args.tracking_uri or cfg.mlflow_tracking_uri)
    mlflow.set_experiment(args.experiment)
    state = load_checkpoint(args.checkpoint)

    for index, params in enumerate(candidates[: args.trials]):
        key = trial_key("study", params, base_seed)
        if key in state["completed"]:
            print(f"study trial {index}: already complete; resumed from checkpoint")
            continue
        if state["spent_thb"] + projected_trial_cost > args.budget_thb:
            raise RuntimeError(
                "budget guard stopped before the next trial: "
                f"spent={state['spent_thb']:.4f}, projected={projected_trial_cost:.4f}, "
                f"limit={args.budget_thb:.2f} THB"
            )

        result = _run_trial(
            phase="study",
            index=index,
            params=params,
            seed=base_seed,
            train_df=train_df,
            val_df=val_df,
            test_df=test_df,
            rate_thb_h=rate_thb_h,
            instance=instance,
            provenance=provenance,
        )
        state["completed"][key] = result
        state["spent_thb"] += result["cost_thb"]
        save_checkpoint(args.checkpoint, state)
        print(
            f"study trial {index}: {params} -> {SELECTION_METRIC}="
            f"{result[SELECTION_METRIC]:.6f}, cost={result['cost_thb']:.6f} THB"
        )

        study_count = sum(
            item["phase"] == "study" for item in state["completed"].values()
        )
        if (
            args.interrupt_after
            and study_count >= args.interrupt_after
            and not state.get("interruption_recorded")
        ):
            state["interruption_recorded"] = {
                "after_study_trials": study_count,
                "checkpoint": str(args.checkpoint),
                "kind": "intentional resumability evidence",
            }
            save_checkpoint(args.checkpoint, state)
            raise RuntimeError(
                "intentional interruption after checkpoint; rerun with the same output path"
            )

    study_results = [
        item for item in state["completed"].values() if item["phase"] == "study"
    ]
    if len(study_results) != args.trials:
        raise RuntimeError(f"expected {args.trials} completed study trials, got {len(study_results)}")

    selected = select_candidate(study_results, args.selection_tolerance)
    MlflowClient().set_tag(selected["run_id"], "selected_candidate", "true")

    for offset in range(args.seed_repeats):
        repeat_seed = base_seed + offset
        key = trial_key("seed", selected["params"], repeat_seed)
        if key in state["completed"]:
            print(f"seed {repeat_seed}: already complete; resumed from checkpoint")
            continue
        if state["spent_thb"] + projected_trial_cost > args.budget_thb:
            raise RuntimeError("budget guard stopped before completing the seed study")

        train_repeat, val_repeat, test_repeat = data.split(frame, seed=repeat_seed)
        result = _run_trial(
            phase="seed",
            index=offset,
            params=selected["params"],
            seed=repeat_seed,
            train_df=train_repeat,
            val_df=val_repeat,
            test_df=test_repeat,
            rate_thb_h=rate_thb_h,
            instance=instance,
            provenance=provenance,
        )
        state["completed"][key] = result
        state["spent_thb"] += result["cost_thb"]
        save_checkpoint(args.checkpoint, state)
        print(
            f"seed {repeat_seed}: {SELECTION_METRIC}={result[SELECTION_METRIC]:.6f}, "
            f"cost={result['cost_thb']:.6f} THB"
        )

    seed_results = [
        item for item in state["completed"].values() if item["phase"] == "seed"
    ]
    seed_values = [item[SELECTION_METRIC] for item in seed_results]
    summary = {
        "experiment": args.experiment,
        "selection_metric": SELECTION_METRIC,
        "selection_rule": (
            f"lowest measured training cost within {args.selection_tolerance:.4f} "
            f"absolute {SELECTION_METRIC} of the best study run"
        ),
        "selected": selected,
        "study_trials": len(study_results),
        "seed_trials": len(seed_results),
        "seed_mean": statistics.fmean(seed_values),
        "seed_population_sd": statistics.pstdev(seed_values),
        "seed_min": min(seed_values),
        "seed_max": max(seed_values),
        "seed_spread": max(seed_values) - min(seed_values),
        "estimated_total_trial_cost_thb": state["spent_thb"],
        "monthly_selected_retrain_estimate_thb": statistics.fmean(
            item["cost_thb"] for item in seed_results
        ),
        "price_evidence": costs.VERIFIED_PRICE.__dict__,
        "interruption": state.get("interruption_recorded"),
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
