"""Unit tests for Azure resource setup without contacting Azure."""
from __future__ import annotations

import pytest

from cloudlayer import azure
from scripts.bootstrap_azureml import _dedicated_compute


def test_acr_resource_id_resolves_dnl_hashed_login_server(monkeypatch):
    login_server = f"course-registry-examplehash{azure.ACR_LOGIN_SUFFIX}"
    resource_id = (
        "/subscriptions/example/resourceGroups/course-lab/providers/"
        "Microsoft.ContainerRegistry/registries/course-registry"
    )
    calls: list[list[str]] = []

    def fake_run_output(args: list[str]) -> str:
        calls.append(args)
        return resource_id

    monkeypatch.setattr(azure, "_run_output", fake_run_output)

    assert azure._acr_resource_id(login_server) == resource_id
    assert calls == [
        [
            "az",
            "acr",
            "list",
            "--query",
            f"[?loginServer=='{login_server}'].id | [0]",
            "-o",
            "tsv",
        ]
    ]


def test_acr_resource_id_rejects_missing_registry(monkeypatch):
    monkeypatch.setattr(azure, "_run_output", lambda _args: "")

    with pytest.raises(RuntimeError, match="no accessible ACR"):
        azure._acr_resource_id(f"missing{azure.ACR_LOGIN_SUFFIX}")


def test_acr_resource_id_rejects_non_acr_hostname():
    with pytest.raises(ValueError, match="must end with"):
        azure._acr_resource_id("registry.example.com")


def test_dedicated_compute_has_scale_to_zero_system_identity():
    compute = _dedicated_compute("course-compute", {"course": "example"})

    assert compute.size == "Standard_DS2_v2"
    assert compute.min_instances == 0
    assert compute.max_instances == 1
    assert compute.idle_time_before_scale_down == 120
    assert compute.tier == "dedicated"
    assert compute.identity.type.value == "SystemAssigned"
