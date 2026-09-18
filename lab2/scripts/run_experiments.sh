#!/usr/bin/env bash
set -euo pipefail

image_ref="${IMAGE_REF:?IMAGE_REF is required}"
git_commit="${GIT_COMMIT:?GIT_COMMIT is required}"
seed="${SEED:-20260101}"
mlflow_volume="${MLFLOW_VOLUME:-itcs355-lab1-mlflow}"

if [[ ! -f data/raw/sensors.csv ]]; then
  echo "FAIL: data/raw/sensors.csv is missing; run 'dvc pull data/raw.dvc'" >&2
  exit 1
fi

run_experiment() {
  local run_name="$1"
  local n_estimators="$2"
  local max_depth="$3"
  local min_samples_leaf="$4"

  printf '\n=== run=%s trees=%s depth=%s leaf=%s seed=%s ===\n' \
    "$run_name" "$n_estimators" "$max_depth" "$min_samples_leaf" "$seed"

  docker run --rm \
    -w /app/reports \
    -v "$PWD/data/raw:/app/data/raw:ro" \
    -v "$PWD/reports:/app/reports" \
    -v "$mlflow_volume:/app/reports/mlruns" \
    -e GIT_COMMIT="$git_commit" \
    -e PYTHONHASHSEED="$seed" \
    -e MLFLOW_TRACKING_URI=sqlite:////app/reports/mlflow.db \
    "$image_ref" \
    --experiment itcs355-lab1 \
    --run-name "$run_name" \
    --n-estimators "$n_estimators" \
    --max-depth "$max_depth" \
    --min-samples-leaf "$min_samples_leaf" \
    --seed "$seed" \
    --metrics-out "/app/reports/metrics-${run_name}.json"
}

# Pre-declared matrix: change one capacity/regularisation factor at a time.
run_experiment baseline 200 8 5
run_experiment fewer-trees 100 8 5
run_experiment more-trees 300 8 5
run_experiment shallow 200 4 5
run_experiment larger-leaf 200 8 10

echo "PASS: completed 5/5 MLflow experiment runs"
