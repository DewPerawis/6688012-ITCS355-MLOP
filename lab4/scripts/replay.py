"""Send real requests to local or managed service and timestamp deliberate drift."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from src import config
from src.contracts import validate_features
from src.data import FEATURES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8080/predict/batch")
    parser.add_argument("--shift", type=float, default=0)
    parser.add_argument("--rows", type=int, default=600)
    parser.add_argument("--pause", type=float, default=0.2)
    args = parser.parse_args()
    if args.rows < 500 or args.pause < 0:
        parser.error("use at least 500 rows and a nonnegative pause")
    # A deterministic independent sample, rather than the first correlated machines.
    reference = pd.read_csv("data/reference.csv")
    frame = reference.sample(n=args.rows, replace=True, random_state=7)[FEATURES].copy()
    frame["temp_c"] += args.shift
    validate_features(frame)
    cfg = config.load(strict=args.cloud)
    if args.cloud:
        from cloudlayer.factory import get_adapter

        adapter = get_adapter(cfg)
    evidence = {"kind": "injection" if args.shift else "baseline",
                "started_at": datetime.now(UTC).isoformat(), "shift_temp_c": args.shift,
                "rows_planned": len(frame), "rows_sent": 0,
                "target": cfg.online_endpoint if args.cloud else "local",
                "model_version": cfg.model_version if args.cloud else os.getenv("MODEL_VERSION", "local"),
                "simulation": True, "source": "controlled replay of training-only synthetic inputs"}
    target = Path("reports/injection.json" if args.shift else "reports/baseline-replay.json")
    target.parent.mkdir(exist_ok=True)
    try:
        for start in range(0, len(frame), 50):
            batch = frame.iloc[start:start + 50]
            payload = {"rows": batch.to_dict(orient="records")}
            if args.cloud:
                result = adapter.invoke(cfg.online_endpoint, payload)
            else:
                request = Request(args.url, data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=30) as response:
                    result = json.load(response)
            assert len(result["probabilities"]) == len(batch), "incomplete batch response"
            assert all(0 <= value <= 1 for value in result["probabilities"])
            if args.cloud:
                assert str(result["model_version"]) == cfg.model_version, "wrong model version"
            evidence["rows_sent"] += len(batch)
            print(f"replayed {evidence['rows_sent']}/{len(frame)} shift={args.shift}", flush=True)
            time.sleep(args.pause)
        evidence["completed_at"] = datetime.now(UTC).isoformat()
    finally:
        target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Saved {target}; injected requests must reach dashboard and scheduled detector")


if __name__ == "__main__":
    main()
