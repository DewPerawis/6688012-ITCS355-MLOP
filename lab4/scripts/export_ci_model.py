"""Export an ephemeral integration fixture, distinct from the registered model."""
from pathlib import Path

import joblib
import mlflow.sklearn

from src.data import FEATURES

if __name__ == "__main__":
    path = Path("reports/ci-model-mlflow")
    if path.exists():
        raise SystemExit("CI export already exists; reuse it or choose a fresh working tree")
    # This fixture is trained by this CI run; keep its format compatible with
    # the serving image instead of relying on MLflow's default serialization.
    mlflow.sklearn.save_model(
        joblib.load("reports/ci-model.joblib"), str(path), serialization_format="cloudpickle"
    )
    print(f"Saved CI-only MLflow fixture to {path}; feature order={FEATURES}")
