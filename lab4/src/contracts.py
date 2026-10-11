"""Explicit training and serving data contracts; violations fail before scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data import FEATURES, GROUP, PLAUSIBLE_RANGES, TARGET


def validate_features(frame: pd.DataFrame) -> None:
    if set(frame.columns) != set(FEATURES):
        raise ValueError(f"feature schema mismatch: expected {FEATURES}, got {list(frame.columns)}")
    if frame.empty:
        raise ValueError("input window is empty")
    for name in FEATURES:
        if not pd.api.types.is_numeric_dtype(frame[name]) or pd.api.types.is_bool_dtype(frame[name]):
            raise ValueError(f"{name}: numeric dtype required")
        values = frame[name].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"{name}: null/non-finite rate must be zero")
        lower, upper = PLAUSIBLE_RANGES[name]
        if not ((values >= lower) & (values <= upper)).all():
            raise ValueError(f"{name}: outside [{lower}, {upper}]")


def validate_training(frame: pd.DataFrame) -> None:
    expected = set(FEATURES) | {"reading_id", GROUP, TARGET}
    if set(frame.columns) != expected:
        raise ValueError(f"training schema mismatch: expected {sorted(expected)}")
    validate_features(frame[FEATURES])
    for name in ("reading_id", GROUP, TARGET):
        if not pd.api.types.is_integer_dtype(frame[name]) or frame[name].isna().any():
            raise ValueError(f"{name}: non-null integer required")
    if not frame[TARGET].isin([0, 1]).all():
        raise ValueError("target must be binary")
    if frame["reading_id"].duplicated().any():
        raise ValueError("reading_id must be unique")
