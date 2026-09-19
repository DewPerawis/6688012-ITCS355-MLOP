"""Unit tests for Azure resource-name resolution without contacting Azure."""
from __future__ import annotations

import pytest

from cloudlayer import azure


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
