import numpy as np
import pytest

from monitoring.drift import ks_statistic, psi
from scripts.make_dataset import build
from src.data import split


def test_group_split_is_deterministic():
    frame = build(20260101)
    first, second = split(frame), split(frame)
    assert all(a.equals(b) for a, b in zip(first, second, strict=True))


def test_identical_distributions_have_zero_drift():
    values = np.arange(100, dtype=float)
    assert psi(values, values) == pytest.approx(0)
    assert ks_statistic(values, values) == pytest.approx(0)


def test_constant_reference_still_detects_a_shift():
    assert psi(np.ones(100), np.full(100, 2.0)) > 0.1


def test_empty_window_is_not_reported_as_stable():
    with pytest.raises(ValueError, match="non-empty"):
        psi(np.array([]), np.arange(10))
