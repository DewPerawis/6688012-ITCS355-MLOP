"""Azure adapter decisions tested without contacting Azure."""
import pytest

from cloudlayer.azure import _model_mount_path, _model_ref, _validate_traffic


def test_model_reference_requires_exact_integer_version():
    assert _model_ref("itcs355-6688012:2") == ("itcs355-6688012", "2")
    with pytest.raises(ValueError):
        _model_ref("itcs355-6688012:latest")


def test_model_mount_path_rejects_unsafe_values():
    assert _model_mount_path("itcs355-6688012", "2") == (
        "/var/azureml-app/azureml-models/itcs355-6688012/2/model"
    )
    with pytest.raises(ValueError):
        _model_mount_path("../secret", "2")
    assert _model_mount_path("itcs355-6688012", "2", "") == (
        "/var/azureml-app/azureml-models/itcs355-6688012/2"
    )


def test_traffic_must_total_exactly_100():
    assert _validate_traffic({"blue": 90, "green": 10}) == {"blue": 90, "green": 10}
    with pytest.raises(ValueError):
        _validate_traffic({"blue": 90, "green": 9})
    with pytest.raises(ValueError):
        _validate_traffic({"blue": 110, "green": -10})
