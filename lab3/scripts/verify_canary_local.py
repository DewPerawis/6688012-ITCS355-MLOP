"""Download and score the registered canary without creating cloud compute."""
from __future__ import annotations

import json
from pathlib import Path

import mlflow.sklearn
import pandas as pd

from cloudlayer.factory import get_adapter
from scripts.smoke import PAYLOADS
from src import config
from src.data import FEATURES


def main() -> int:
    cfg = config.load()
    evidence = json.loads(
        Path("reports/lab3-canary-model.json").read_text(encoding="utf-8")
    )
    version = str(evidence["version"])
    local_path = get_adapter(cfg).download_model(
        cfg.model_registry_name,
        version,
        f"reports/model-v{version}",
    )
    model = mlflow.sklearn.load_model(local_path)
    frame = pd.DataFrame.from_records(PAYLOADS, columns=FEATURES)
    probabilities = [float(value) for value in model.predict_proba(frame)[:, 1]]
    if len(probabilities) != 3 or not all(0 <= value <= 1 for value in probabilities):
        raise RuntimeError("canary model returned invalid probabilities")
    relative_path = Path(local_path).resolve().relative_to(Path.cwd().resolve())
    print("CANARY LOCAL SUMMARY")
    print(f"version={version}")
    print(f"mlmodel_parent={relative_path.as_posix()}")
    print("probabilities=" + ",".join(f"{value:.6f}" for value in probabilities))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
