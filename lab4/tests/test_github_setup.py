"""Managed-identity setup must avoid directory operations and keep preview read-only."""
import json
from types import SimpleNamespace

import pytest

from cloudlayer import github_setup


@pytest.fixture()
def setup(monkeypatch):
    mutations = []
    reads = []
    cfg = SimpleNamespace(azure_resource_group="lab-rg", azureml_workspace="lab-workspace",
                          container_registry="registry.invalid/lab", azure_subscription_id="subscription-id")
    monkeypatch.setattr(github_setup.config, "load", lambda: cfg)

    def read(*args):
        reads.append(args)
        assert args[:2] != ("az", "ad"), "managed identity must not use directory lookups"
        if args[:3] == ("gh", "repo", "view"):
            return "example/student"
        if args[:3] == ("az", "account", "show"):
            return "tenant-id"
        if args[:3] == ("az", "identity", "show"):
            return json.dumps({"clientId": "client-id", "principalId": "principal-id", "id": "/identity/ci"})
        if args[:3] == ("az", "acr", "list"):
            return json.dumps({"name": "registry", "id": "/registry/r"})
        if args[:4] == ("az", "ml", "workspace", "show"):
            return "/workspace/w"
        if args[:4] == ("az", "identity", "federated-credential", "list"):
            return "[]"
        pytest.fail(f"unexpected read: {args}")

    monkeypatch.setattr(github_setup, "output", read)
    monkeypatch.setattr(github_setup.subprocess, "run", lambda command, **kwargs:
                        mutations.append((command, kwargs)))
    return reads, mutations


def test_managed_identity_preview_does_not_modify_azure_or_github(setup, monkeypatch):
    monkeypatch.setattr("sys.argv", ["github_setup", "--managed-identity", "lab4-ci"])
    github_setup.main()
    reads, mutations = setup
    assert reads
    assert mutations == []


def test_managed_identity_execution_uses_arm_federation_and_scoped_roles(setup, monkeypatch):
    monkeypatch.setattr("sys.argv", ["github_setup", "--managed-identity", "lab4-ci", "--execute"])
    github_setup.main()
    _, mutations = setup
    commands = [command for command, _ in mutations]
    assert all(command[:2] != ["az", "ad"] for command in commands)
    federation = next(command for command in commands
                      if command[:4] == ["az", "identity", "federated-credential", "create"])
    assert federation[federation.index("--subject") + 1] == "repo:example/student:environment:staging"
    roles = [command for command in commands if command[:4] == ["az", "role", "assignment", "create"]]
    assert {command[command.index("--scope") + 1] for command in roles} == {"/workspace/w", "/registry/r"}
    switch = next(command for command in commands if command[:4] == ["gh", "variable", "set", "LAB4_DEPLOY_ENABLED"])
    assert switch[switch.index("--body") + 1] == "false"
