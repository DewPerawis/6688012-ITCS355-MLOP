"""Run the contract on the generated dataset, not only on mock examples."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.contracts import validate_training
from src.data import FEATURES, GROUP, split


@pytest.fixture(scope="module")
def frame():
    path = Path("data/raw/sensors.csv")
    assert path.is_file(), "Run python -m scripts.make_dataset before tests"
    return pd.read_csv(path)


def test_training_schema_contract(frame):
    validate_training(frame)


def test_plausible_ranges_and_zero_null_contract(frame):
    validate_training(frame)
    broken = frame.copy()
    broken.loc[0, "temp_c"] = 999
    with pytest.raises(ValueError, match="temp_c: outside"):
        validate_training(broken)
    broken = frame.copy()
    broken.loc[0, "temp_c"] = np.nan
    with pytest.raises(ValueError, match="null/non-finite"):
        validate_training(broken)


def test_schema_rejects_missing_and_unknown_features(frame):
    with pytest.raises(ValueError, match="schema mismatch"):
        validate_training(frame.drop(columns=[FEATURES[0]]))
    with pytest.raises(ValueError, match="schema mismatch"):
        validate_training(frame.assign(temperature_f=100))


def test_machine_id_split_has_no_leakage(frame):
    train, validation, test = split(frame)
    sets = [set(part[GROUP]) for part in (train, validation, test)]
    assert all(sets[i].isdisjoint(sets[j]) for i, j in ((0, 1), (0, 2), (1, 2)))
    assert sum(len(part) for part in (train, validation, test)) == len(frame)


def test_labels_and_identifiers_contract(frame):
    broken = frame.copy()
    broken.loc[0, "failed_within_7d"] = 7
    with pytest.raises(ValueError, match="binary"):
        validate_training(broken)
