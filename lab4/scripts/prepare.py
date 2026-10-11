"""Generate CI-only model and training-only reference; never promote this model."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier

from monitoring.drift import calibrate
from scripts.make_dataset import build
from src.contracts import validate_training
from src.data import FEATURES, TARGET, split


def main():
    frame = build(20260101)
    validate_training(frame)
    train, _, _ = split(frame)
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(exist_ok=True)
    frame.to_csv("data/raw/sensors.csv", index=False)
    train.to_csv("data/reference.csv", index=False)
    model = RandomForestClassifier(n_estimators=60, max_depth=8, min_samples_leaf=5,
                                   random_state=20260101, n_jobs=1)
    model.fit(train[FEATURES], train[TARGET])
    joblib.dump(model, "reports/ci-model.joblib")
    result = calibrate(train)
    Path("reports/threshold-calibration.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print("Prepared deterministic dataset, CI fixture model, training-only reference")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
