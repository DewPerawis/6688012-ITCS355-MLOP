"""Local diagnostic rehearsal; no cloud evidence or external alert is claimed."""
import json
from pathlib import Path

import pandas as pd

from monitoring.drift import compare
from src.contracts import validate_features
from src.data import FEATURES

if __name__ == "__main__":
    reference = pd.read_csv("data/reference.csv")[FEATURES]
    baseline = reference.sample(n=500, replace=True, random_state=7).reset_index(drop=True)
    shifted = baseline.copy()
    shifted["temp_c"] += 12
    validate_features(shifted)
    threshold = json.loads(Path("reports/threshold-calibration.json").read_text())["threshold"]
    stable, drift = compare(reference, baseline), compare(reference, shifted)
    assert max(item["psi"] for item in stable) < threshold, "calibration false alert"
    assert next(item for item in drift if item["feature"] == "temp_c")["psi"] >= threshold
    result = {"evidence_type": "local rehearsal only; cloud evidence still required", "threshold": threshold,
              "injected_temp_c_shift": 12, "baseline": stable, "injected": drift,
              "real_channel_alert": False, "scheduled_cloud_job": False}
    Path("reports/local-drift-rehearsal.json").write_text(json.dumps(result, indent=2),
                                                       encoding="utf-8")
    print(json.dumps(result, indent=2))
