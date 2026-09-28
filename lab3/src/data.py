"""Shared inference feature contract carried forward from Lab 2."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = [
    "temp_c",
    "vibration_mm_s",
    "pressure_kpa",
    "hours_since_service",
    "load_pct",
    "ambient_humidity",
]

PLAUSIBLE_RANGES = {
    "temp_c": (-10.0, 140.0),
    "vibration_mm_s": (0.0, 60.0),
    "pressure_kpa": (0.0, 600.0),
    "hours_since_service": (0.0, 20000.0),
    "load_pct": (0.0, 100.0),
    "ambient_humidity": (0.0, 100.0),
}

TARGET = "failed_within_7d"
GROUP = "machine_id"


def load_raw(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"missing dataset: {path}")
    return pd.read_csv(path)


def split(
    frame: pd.DataFrame,
    seed: int = 20260101,
    val_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Reproduce the Lab 2 group-aware partition for canary evaluation."""
    rng = np.random.default_rng(seed)
    groups = np.sort(frame[GROUP].unique())
    shuffled = rng.permutation(groups)
    n_test = int(round(len(shuffled) * test_fraction))
    n_val = int(round(len(shuffled) * val_fraction))
    test_groups = set(shuffled[:n_test])
    val_groups = set(shuffled[n_test : n_test + n_val])
    train_groups = set(shuffled[n_test + n_val :])
    return tuple(
        frame[frame[GROUP].isin(group_set)].reset_index(drop=True)
        for group_set in (train_groups, val_groups, test_groups)
    )
