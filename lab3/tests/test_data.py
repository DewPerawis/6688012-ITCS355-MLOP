"""Regression tests for the carried-forward data contract and grouped split."""
from scripts.make_dataset import build
from src import data


def test_dataset_is_deterministic():
    first = build(20260101)
    second = build(20260101)
    assert first.equals(second)


def test_group_split_has_no_machine_leakage():
    train, validation, test = data.split(build(20260101))
    train_groups = set(train[data.GROUP])
    validation_groups = set(validation[data.GROUP])
    test_groups = set(test[data.GROUP])
    assert train_groups.isdisjoint(validation_groups)
    assert train_groups.isdisjoint(test_groups)
    assert validation_groups.isdisjoint(test_groups)
