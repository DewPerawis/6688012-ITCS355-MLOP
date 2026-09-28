"""Replay labelled validation rows through live traffic and detect version degradation."""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sklearn.metrics import average_precision_score

from cloudlayer.factory import get_adapter
from src import config, data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/raw/sensors.csv"))
    parser.add_argument("--max-requests", type=int, default=600)
    parser.add_argument("--min-version-samples", type=int, default=50)
    parser.add_argument("--drop-threshold", type=float, default=0.005)
    parser.add_argument("--out", type=Path, default=Path("reports/lab3-canary-probe.json"))
    args = parser.parse_args()
    cfg = config.load()
    adapter = get_adapter(cfg)
    _, validation, _ = data.split(data.load_raw(args.data))
    rows = validation.sample(frac=1.0, random_state=20260101).reset_index(drop=True)
    scores: dict[str, list[float]] = defaultdict(list)
    labels: dict[str, list[int]] = defaultdict(list)
    started = time.monotonic()
    started_at = datetime.now(UTC)
    detection: dict | None = None

    for index in range(args.max_requests):
        row = rows.iloc[index % len(rows)]
        payload = {feature: float(row[feature]) for feature in data.FEATURES}
        response = adapter.invoke(cfg.online_endpoint, payload)
        version = str(response["model_version"])
        scores[version].append(float(response["probability"]))
        labels[version].append(int(row[data.TARGET]))
        if (index + 1) % 10 != 0 or len(scores) < 2:
            continue
        if min(map(len, scores.values())) < args.min_version_samples:
            continue
        metrics = {
            key: average_precision_score(labels[key], values)
            for key, values in scores.items()
            if len(set(labels[key])) == 2
        }
        if len(metrics) < 2:
            continue
        best_version = max(metrics, key=metrics.get)
        worst_version = min(metrics, key=metrics.get)
        drop = metrics[best_version] - metrics[worst_version]
        if drop >= args.drop_threshold:
            detection = {
                "detected_at": datetime.now(UTC).isoformat(),
                "elapsed_s": round(time.monotonic() - started, 3),
                "requests": index + 1,
                "metric": "validation_pr_auc",
                "best_version": best_version,
                "worst_version": worst_version,
                "absolute_drop": drop,
                "metrics": metrics,
            }
            break

    summary = {
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "sample_counts": {key: len(value) for key, value in scores.items()},
        "detection": detection,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if detection else 3


if __name__ == "__main__":
    raise SystemExit(main())
