"""Scheduled drift check on actual cloud inference logs; exit nonzero on broken monitoring."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from monitoring.alerts import deliver
from monitoring.drift import compare
from src.data import FEATURES


def main():
    from cloudlayer.observability import recent_inputs, secret_value

    window = int(os.environ.get("DRIFT_WINDOW_ROWS", "500"))
    current_rows = recent_inputs(os.environ["LOG_ANALYTICS_WORKSPACE_ID"],
                                 os.environ["ONLINE_ENDPOINT"], os.environ["MODEL_VERSION"],
                                 rows=window)
    checked = datetime.now(UTC).isoformat()
    Path("outputs").mkdir(exist_ok=True)
    if len(current_rows) < window:
        Path("outputs/drift.json").write_text(json.dumps({"status": "insufficient_data",
            "rows": len(current_rows), "required_rows": window, "checked_at": checked}),
            encoding="utf-8")
        raise RuntimeError("insufficient recent production inputs; monitoring is not green")
    current = pd.DataFrame([row["features"] if isinstance(row["features"], dict)
                            else json.loads(row["features"]) for row in current_rows])[FEATURES]
    reference = pd.read_csv("data/reference.csv")[FEATURES]
    calibration = json.loads(Path("data/calibration.json").read_text())
    threshold = float(calibration["threshold"])
    results = compare(reference, current)
    breached = [item for item in results if item["psi"] >= threshold]
    evidence = {"status": "drift" if breached else "stable", "checked_at": checked,
                "source": "Azure managed endpoint console logs", "rows": len(current),
                "oldest_input_at": min(row["timestamp"] for row in current_rows),
                "newest_input_at": max(row["timestamp"] for row in current_rows),
                "threshold": threshold, "features": results, "alert": None}
    # MLflow is provider-neutral; Azure ML connects this run to its job automatically.
    import mlflow

    with mlflow.start_run():
        for result in results:
            mlflow.log_metric(f"drift.psi.{result['feature']}", result["psi"])
            mlflow.log_metric(f"drift.ks.{result['feature']}", result["ks"])
        mlflow.log_metric("drift.threshold", threshold)
        mlflow.log_metric("drift.alert", int(bool(breached)))
        if breached:
            webhook = secret_value(os.environ["VAULT_URL"], os.environ["ALERT_SECRET_NAME"])
            text = (f"ITCS355 Lab4 drift {checked}; endpoint={os.environ['ONLINE_ENDPOINT']}; "
                    f"model={os.environ['MODEL_VERSION']}; threshold={threshold:.4f}; "
                    + ", ".join(f"{item['feature']} PSI={item['psi']:.4f}" for item in breached))
            evidence["alert"] = deliver(webhook, text)
            evidence["alert_accepted_at"] = datetime.now(UTC).isoformat()
        Path("outputs/drift.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        mlflow.log_artifact("outputs/drift.json")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
