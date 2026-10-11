"""Bounded five-minute request and feature windows for a single service process."""
from __future__ import annotations

import json
import time
from collections import deque
from threading import Lock

import numpy as np

from src.data import FEATURES

LOCK = Lock()
REQUESTS: deque = deque(maxlen=100_000)
INPUTS: deque = deque(maxlen=50_000)
WINDOW_SECONDS = 300


def record_request(path: str, status: int, latency_ms: float, version: str):
    if path not in ("/predict", "/predict/batch", "/invoke"):
        return
    with LOCK:
        REQUESTS.append((time.time(), status, latency_ms, version))


def record_inputs(records: list[dict]):
    now = time.time()
    with LOCK:
        INPUTS.extend((now, row) for row in records)


def reset():
    with LOCK:
        REQUESTS.clear()
        INPUTS.clear()


def snapshot(version: str) -> dict:
    cutoff = time.time() - WINDOW_SECONDS
    with LOCK:
        while REQUESTS and REQUESTS[0][0] < cutoff:
            REQUESTS.popleft()
        while INPUTS and INPUTS[0][0] < cutoff:
            INPUTS.popleft()
        requests, inputs = list(REQUESTS), list(INPUTS)
    latencies = [item[2] for item in requests]
    count = len(requests)
    return {"window_seconds": WINDOW_SECONDS, "request_count": count,
            "request_rate": count / WINDOW_SECONDS,
            "4xx_fraction": sum(400 <= item[1] < 500 for item in requests) / max(count, 1),
            "5xx_fraction": sum(item[1] >= 500 for item in requests) / max(count, 1),
            "latency_ms": {f"p{percentile}": float(np.percentile(latencies, percentile))
                           if latencies else None for percentile in (50, 95, 99)},
            "feature_mean": {feature: float(np.mean([item[1][feature] for item in inputs]))
                             if inputs else None for feature in FEATURES},
            "model_version": version, "feature_rows": len(inputs)}


def prometheus_text(version: str) -> str:
    state = snapshot(version)
    lines = [f'lab4_request_rate {state["request_rate"]}',
             f'lab4_error_fraction{{status_class="4xx"}} {state["4xx_fraction"]}',
             f'lab4_error_fraction{{status_class="5xx"}} {state["5xx_fraction"]}',
             f'lab4_model_info{{version={json.dumps(version)}}} 1']
    for quantile, value in state["latency_ms"].items():
        if value is not None:
            lines.append(f'lab4_latency_ms{{quantile="{quantile}"}} {value}')
    for feature, value in state["feature_mean"].items():
        if value is not None:
            lines.append(f'lab4_feature_mean{{feature="{feature}"}} {value}')
    return "\n".join(lines) + "\n"
