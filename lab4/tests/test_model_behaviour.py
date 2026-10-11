"""CI fixture checks behaviour; the exact registry model is checked separately."""
import numpy as np
import pandas as pd
import pytest

from src.data import FEATURES


@pytest.fixture(scope="module")
def model():
    import os

    import joblib

    if os.environ.get("MODEL_PATH"):
        import mlflow.sklearn

        return mlflow.sklearn.load_model(os.environ["MODEL_PATH"])
    return joblib.load("reports/ci-model.joblib")


def test_healthy_input_scores_low(model):
    healthy = pd.DataFrame([{
        "temp_c": 66, "vibration_mm_s": 1.4, "pressure_kpa": 330,
        "hours_since_service": 150, "load_pct": 35, "ambient_humidity": 50,
    }])[FEATURES]
    score = float(model.predict_proba(healthy)[0, 1])
    assert 0 <= score < 0.25, f"healthy risk too high: {score}"


def test_probabilities_are_finite_bounded_and_not_constant(model):
    frame = pd.read_csv("data/raw/sensors.csv")[FEATURES].head(500)
    proba = model.predict_proba(frame)[:, 1]
    assert np.isfinite(proba).all()
    assert np.all((proba >= 0) & (proba <= 1))
    assert proba.std() > 0.01
