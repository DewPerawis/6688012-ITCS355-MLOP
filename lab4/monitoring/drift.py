"""PSI/KS against a training-only reference, including degenerate features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.contracts import validate_features
from src.data import FEATURES


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    reference, current = np.asarray(reference, dtype=float), np.asarray(current, dtype=float)
    if not len(reference) or not len(current):
        raise ValueError("PSI requires two non-empty windows")
    if not np.isfinite(reference).all() or not np.isfinite(current).all():
        raise ValueError("PSI requires finite inputs")
    internal = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)[1:-1]))
    if len(np.unique(reference)) == 1:
        center = float(reference[0])
        epsilon = max(abs(center) * 1e-6, 1e-6)
        internal = np.array([center - epsilon, center + epsilon])
    edges = np.r_[-np.inf, internal, np.inf]
    ref_counts = np.histogram(reference, bins=edges)[0]
    cur_counts = np.histogram(current, bins=edges)[0]
    ref_prop = (ref_counts + 1) / (len(reference) + len(ref_counts))
    cur_prop = (cur_counts + 1) / (len(current) + len(cur_counts))
    return float(np.sum((cur_prop - ref_prop) * np.log(cur_prop / ref_prop)))


def ks_statistic(reference: np.ndarray, current: np.ndarray) -> float:
    reference, current = np.sort(reference), np.sort(current)
    if not len(reference) or not len(current):
        raise ValueError("KS requires two non-empty windows")
    pooled = np.r_[reference, current]
    return float(np.max(np.abs(
        np.searchsorted(reference, pooled, side="right") / len(reference)
        - np.searchsorted(current, pooled, side="right") / len(current)
    )))


def compare(reference: pd.DataFrame, current: pd.DataFrame) -> list[dict]:
    validate_features(reference)
    validate_features(current)
    return [
        {"feature": feature, "psi": psi(reference[feature], current[feature]),
         "ks": ks_statistic(reference[feature].to_numpy(), current[feature].to_numpy()),
         "reference_mean": float(reference[feature].mean()),
         "current_mean": float(current[feature].mean())}
        for feature in FEATURES
    ]


def calibrate(reference: pd.DataFrame, window: int = 500, repeats: int = 200,
              seed: int = 20260101) -> dict:
    """Null calibration over the maximum PSI across all six features.

    Rows from synthetic machines are correlated: resample complete machines in the
    caller's frame, rather than treating every sensor reading as independent.
    """
    from src.data import GROUP

    if GROUP not in reference:
        raise ValueError("calibration needs machine_id for cluster bootstrap")
    groups = reference[GROUP].unique()
    rng = np.random.default_rng(seed)
    sizes = reference.groupby(GROUP).size()
    per_group = float(sizes.mean())
    maxima = []
    for _ in range(repeats):
        sampled = rng.choice(groups, size=max(1, int(np.ceil(window / per_group))), replace=True)
        current = pd.concat([reference[reference[GROUP] == group] for group in sampled])
        current = current.head(window)[FEATURES]
        maxima.append(max(item["psi"] for item in compare(reference[FEATURES], current)))
    quantile = float(np.quantile(maxima, 0.99))
    return {"threshold": max(0.10, quantile * 1.5), "null_max_psi_p99": quantile,
            "margin": 1.5, "floor": 0.10, "window_rows": window,
            "bootstrap_repeats": repeats, "seed": seed,
            "reference": "training machines only", "method": "cluster bootstrap; max over six features",
            "limitations": "in-sample synthetic calibration; confirm false alerts on real windows"}
