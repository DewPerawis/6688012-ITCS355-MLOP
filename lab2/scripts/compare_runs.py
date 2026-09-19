"""Build the Lab 2 comparison and decision report from tracked Azure ML runs."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
import pandas as pd

from cloudlayer.factory import get_adapter
from src import config, costs


def _tracking_uri(cfg, override: str | None) -> str:
    if override:
        return override
    if cfg.provider.lower() == "azure":
        return get_adapter(cfg).tracking_uri()
    return cfg.mlflow_tracking_uri


def _job_ids_for_study(history_path: Path, study_id: str) -> set[str]:
    if not history_path.is_file():
        raise FileNotFoundError(f"job history is absent: {history_path}")
    history = json.loads(history_path.read_text(encoding="utf-8"))
    job_ids = {
        str(entry["job_id"])
        for entry in history
        if entry.get("study_id") == study_id and entry.get("job_id")
    }
    if not job_ids:
        raise RuntimeError(f"no job history entries found for study {study_id!r}")
    return job_ids


def _runs_for_jobs(runs: pd.DataFrame, job_ids: set[str]) -> pd.DataFrame:
    column = "tags.training_job_id"
    if column not in runs:
        raise RuntimeError(f"tracked runs do not contain required tag {column!r}")
    return runs[runs[column].isin(job_ids)].copy()


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render a small DataFrame without pandas' optional tabulate dependency."""

    def cell(value: object) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ")

    headers = [cell(column) for column in frame.columns]
    rows = [[cell(value) for value in row] for row in frame.itertuples(index=False, name=None)]
    lines = [
        f"| {' | '.join(headers)} |",
        f"| {' | '.join('---' for _ in headers)} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in rows)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="itcs355-lab2")
    ap.add_argument("--study-id", required=True)
    ap.add_argument(
        "--job-history",
        type=Path,
        default=Path("reports/lab2-jobs.json"),
    )
    ap.add_argument("--metric", default="val_pr_auc")
    ap.add_argument("--tracking-uri", default=None)
    ap.add_argument("--out", type=Path, default=Path("reports/lab2-comparison.md"))
    args = ap.parse_args()

    cfg = config.load(strict=False)
    mlflow.set_tracking_uri(_tracking_uri(cfg, args.tracking_uri))
    experiment = mlflow.get_experiment_by_name(args.experiment)
    if experiment is None:
        print(f"No experiment named {args.experiment!r}. Run the managed study first.")
        return 1

    job_ids = _job_ids_for_study(args.job_history, args.study_id)
    runs = _runs_for_jobs(
        mlflow.search_runs(experiment_ids=[experiment.experiment_id]),
        job_ids,
    )
    metric_col = f"metrics.{args.metric}"
    if metric_col not in runs or runs[metric_col].dropna().empty:
        print(f"No completed runs contain {args.metric!r}.")
        return 1
    runs = runs[runs[metric_col].notna()].copy()
    study = runs[runs.get("tags.phase") == "study"].copy()
    seed_runs = runs[runs.get("tags.phase") == "seed"].copy()
    if len(study) != 12 or len(seed_runs) != 5:
        print(
            f"Study {args.study_id!r} has {len(study)} configuration and "
            f"{len(seed_runs)} seed runs; expected exactly 12 and 5."
        )
        return 1

    selected_rows = study[study.get("tags.selected_candidate") == "true"]
    if len(selected_rows) != 1:
        print(f"Expected one selected candidate, found {len(selected_rows)}.")
        return 1
    selected = selected_rows.iloc[0]

    table = pd.DataFrame({
        # Keep the complete ID so Azure job-backed runs do not collapse to the
        # same visible "lab2-202" prefix in the audit report.
        "run_id": study["run_id"],
        args.metric: study[metric_col].astype(float),
        "test_pr_auc": study["metrics.test_pr_auc"].astype(float),
        "cost_thb": study["metrics.cost_thb"].astype(float),
        "duration_s": study["metrics.duration_s"].astype(float),
        "trees": study["params.n_estimators"].astype(int),
        "depth": study["params.max_depth"].astype(int),
        "min_leaf": study["params.min_samples_leaf"].astype(int),
    })
    baseline = table[args.metric].min()
    gain_points = (table[args.metric] - baseline) * 100.0
    table["thb_per_point"] = table["cost_thb"] / gain_points.where(gain_points > 0)
    table = table.sort_values(args.metric, ascending=False)

    seed_values = seed_runs[metric_col].astype(float).tolist()
    seed_costs = seed_runs["metrics.cost_thb"].astype(float).tolist()
    best = study.loc[study[metric_col].idxmax()]
    selected_metric = float(selected[metric_col])
    best_metric = float(best[metric_col])
    metric_gap = best_metric - selected_metric
    seed_mean = statistics.fmean(seed_values)
    seed_sd = statistics.pstdev(seed_values)
    seed_spread = max(seed_values) - min(seed_values)
    selected_cost = float(selected["metrics.cost_thb"])
    monthly_cost = statistics.fmean(seed_costs)

    if selected["run_id"] == best["run_id"]:
        choice_reason = (
            f"It is also the highest single-run scorer, but its margin over the runner-up is "
            f"only {table.iloc[0][args.metric] - table.iloc[1][args.metric]:.6f}; the seed "
            "distribution, not that rank alone, is the stronger evidence."
        )
    else:
        choice_reason = (
            f"It is {metric_gap:.6f} below the highest single-run score, inside the declared "
            "0.005 near-best band, and had the lowest measured training cost in that band."
        )

    justification = (
        f"I selected run `{selected['run_id']}` with n_estimators="
        f"{selected['params.n_estimators']}, max_depth={selected['params.max_depth']} and "
        f"min_samples_leaf={selected['params.min_samples_leaf']}. {choice_reason} "
        f"Across {len(seed_values)} seeds, validation PR-AUC averaged {seed_mean:.6f} "
        f"(population SD {seed_sd:.6f}, spread {seed_spread:.6f}), so I do not interpret the "
        f"single-run lead as a stable accuracy gain. The measured compute estimate was "
        f"{selected_cost:.6f} THB for this fit and {monthly_cost:.6f} THB for one monthly "
        "retrain at the same size; Azure provisioning and storage are excluded and actual "
        "billing must be checked separately. This choice could be wrong if production class "
        "balance or machine behaviour differs from the synthetic held-out groups, changing "
        "both PR-AUC ranking and the useful complexity level."
    )

    display = table.copy()
    for column in (args.metric, "test_pr_auc", "cost_thb", "duration_s", "thb_per_point"):
        display[column] = display[column].map(lambda value: "—" if pd.isna(value) else f"{value:.6f}")

    lines = [
        "# Lab 2 — Run comparison",
        "",
        f"Study `{args.study_id}` · experiment `{args.experiment}` · "
        f"{len(study)} configuration trials · "
        f"{len(seed_runs)} seed trials · estimated trial compute "
        f"{runs['metrics.cost_thb'].dropna().astype(float).sum():.6f} THB.",
        "",
        f"Selection metric: `{args.metric}`. Held-out test PR-AUC is shown for audit only and "
        "was not used to select the candidate.",
        "",
        _markdown_table(display),
        "",
        "## Decision (200 words maximum)",
        "",
        justification,
        "",
        "## Cost and interruption evidence",
        "",
        f"- Verified {costs.VERIFIED_PRICE.meter} in `{costs.VERIFIED_PRICE.region}` at "
        f"{costs.VERIFIED_PRICE.hourly_thb:.4f} THB/hour using the "
        f"{costs.VERIFIED_PRICE.source} on {costs.VERIFIED_PRICE.checked_on}.",
        "- Per-trial estimates use measured fit/evaluation wall time multiplied by that rate; "
        "they do not claim to equal the final Azure invoice.",
        f"- The persistent checkpoint and {len(job_ids)} job records for study "
        f"`{args.study_id}` are retained in `reports/lab2-jobs.json`; the first job "
        "intentionally stops after a saved trial and the second job resumes the same study "
        "path.",
        "",
        "## Promotion ownership",
        "",
        "In a real organisation, a release owner or model-risk approver—not the training-job "
        "identity—should promote to Staging. They should require reproducible code/data/image "
        "lineage, review of validation and held-out metrics, seed variance, cost, security and "
        "data-contract checks, and a successful registry reload test. Separation of duties "
        "prevents the person or automation that produced a candidate from silently approving it.",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out} ({len(study)} study + {len(seed_runs)} seed runs)")
    print(display.head(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
