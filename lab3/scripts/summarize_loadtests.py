"""Print a compact, paste-ready summary from k6 summary-export evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPORTS = Path("reports")
TESTS = (
    ("single-1VU", "k6-vus1.json"),
    ("single-5VU", "k6-vus5.json"),
    ("single-7VU", "k6-vus7.json"),
    ("single-8VU", "k6-vus8.json"),
    ("single-9VU", "k6-vus9.json"),
    ("single-10VU", "k6-vus10.json"),
    ("single-10VU-DS3", "k6-vus10-ds3.json"),
    ("single-50VU", "k6-vus50.json"),
    ("batch100-1VU", "k6-batch100-vus1.json"),
    ("payload10KB-1VU", "k6-payload-10kb.json"),
    ("payload100KB-1VU", "k6-payload-100kb.json"),
)


def _number(metrics: dict[str, Any], metric: str, field: str, default: float = 0.0) -> float:
    return float(metrics.get(metric, {}).get(field, default))


def main() -> int:
    print("LOAD TEST SUMMARY (60-second measured windows)")
    print("| test | successes | predictions/s | p50 ms | p95 ms | p99 ms | errors | 429 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    found = 0
    for label, filename in TESTS:
        path = REPORTS / filename
        if not path.exists():
            continue
        metrics = json.loads(path.read_text(encoding="utf-8"))["metrics"]
        successes = int(_number(metrics, "predictions_total", "count"))
        p50 = _number(metrics, "predict_latency_ms", "med")
        p95 = _number(metrics, "predict_latency_ms", "p(95)")
        p99 = _number(metrics, "predict_latency_ms", "p(99)")
        error_pct = _number(metrics, "predict_failures", "value") * 100
        status_429 = int(_number(metrics, "http_status_429", "count"))
        print(
            f"| {label} | {successes} | {successes / 60:.2f} | "
            f"{p50:.2f} | {p95:.2f} | {p99:.2f} | {error_pct:.2f}% | {status_429} |"
        )
        found += 1
    if found == 0:
        raise FileNotFoundError("no completed k6 summary files found")
    print("Note: predictions/s uses successful predictions divided by 60 measured seconds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
