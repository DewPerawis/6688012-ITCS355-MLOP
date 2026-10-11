"""Export an ephemeral integration fixture, distinct from the registered model."""
from pathlib import Path

import joblib
import mlflow.sklearn

from src.data import FEATURES

if __name__ == "__main__":
    path = Path("reports/ci-model-mlflow")
    if path.exists():
        raise SystemExit("CI export already exists; reuse it or choose a fresh working tree")
    mlflow.sklearn.save_model(joblib.load("reports/ci-model.joblib"), str(path))
    print(f"Saved CI-only MLflow fixture to {path}; feature order={FEATURES}")
