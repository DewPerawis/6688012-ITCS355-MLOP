"""Unit tests for Azure resource setup without contacting Azure."""
from __future__ import annotations

from types import SimpleNamespace

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


def test_datastore_uri_uses_safe_versioned_path():
    uri = azure._datastore_uri("course-data", "project", "lab2", "data.csv")

    assert uri.startswith(azure.AZUREML_DATASTORE_PREFIX)
    assert uri.endswith("/course-data/paths/project/lab2/data.csv")


@pytest.mark.parametrize("part", ("../secret", "/absolute", "folder/../../secret"))
def test_datastore_uri_rejects_unsafe_path(part):
    with pytest.raises(ValueError, match="unsafe blob key"):
        azure._datastore_uri("course-data", part)


def test_role_assignment_is_not_recreated_when_present(monkeypatch):
    assignment_id = "/subscriptions/example/providers/authorization/assignments/existing"
    calls: list[list[str]] = []

    def fake_run_output(args: list[str]) -> str:
        calls.append(args)
        return assignment_id

    monkeypatch.setattr(azure, "_run_output", fake_run_output)

    action = azure._ensure_role_assignment(
        "principal-example",
        azure.BLOB_DATA_CONTRIBUTOR_ROLE,
        "/subscriptions/example/resourceGroups/course-lab",
    )

    assert action == "verified"
    assert len(calls) == 1
    assert calls[0][:4] == ["az", "role", "assignment", "list"]


def test_role_assignment_is_created_when_absent(monkeypatch):
    assignment_id = "/subscriptions/example/providers/authorization/assignments/new"
    calls: list[list[str]] = []

    def fake_run_output(args: list[str]) -> str:
        calls.append(args)
        return "" if "list" in args else assignment_id

    monkeypatch.setattr(azure, "_run_output", fake_run_output)

    action = azure._ensure_role_assignment(
        "principal-example",
        azure.BLOB_DATA_CONTRIBUTOR_ROLE,
        "/subscriptions/example/resourceGroups/course-lab",
    )

    assert action == "created"
    assert len(calls) == 2
    assert calls[1][:4] == ["az", "role", "assignment", "create"]
    assert "--assignee-object-id" in calls[1]
    assert "--assignee-principal-type" in calls[1]


def test_training_environment_injects_cloud_runtime_configuration():
    cfg = SimpleNamespace(
        provider="azure",
        region="centralindia",
        training_instance="Standard_DS2_v2-dedicated",
        mlflow_tracking_uri="azureml://tracking/example",
    )
    args = {
        "data_version": "data-version-example",
        "git_commit": "commit-example",
        "seed": 1234,
    }
    image_uri = "registry.example/course@sha256:digest-example"

    environment = azure._training_environment(
        cfg,
        args,
        image_uri,
        "job-example",
        "azureml://tracking/example",
    )

    assert environment == {
        "CLOUD_PROVIDER": "azure",
        "REGION": "centralindia",
        "TRAINING_INSTANCE": "Standard_DS2_v2-dedicated",
        "MLFLOW_TRACKING_URI": "azureml://tracking/example",
        "GIT_COMMIT": "commit-example",
        "DATA_VERSION": "data-version-example",
        "TRAINING_JOB_ID": "job-example",
        "IMAGE_DIGEST": "sha256:digest-example",
        "PYTHONHASHSEED": "1234",
    }


def test_training_environment_rejects_local_tracking_uri():
    cfg = SimpleNamespace(
        provider="azure",
        region="centralindia",
        training_instance="Standard_DS2_v2-dedicated",
    )

    with pytest.raises(ValueError, match="Azure ML tracking URI"):
        azure._training_environment(
            cfg,
            {"data_version": "data-version-example"},
            "registry.example/course@sha256:digest-example",
            "job-example",
            "sqlite:///mlflow.db",
        )


def test_wait_for_terminal_job_polls_past_interim_status(monkeypatch):
    statuses = iter(("Running", "Finalizing", "Failed"))
    jobs = SimpleNamespace(
        get=lambda _job_id: SimpleNamespace(status=next(statuses))
    )
    client = SimpleNamespace(jobs=jobs)
    sleeps: list[float] = []

    monkeypatch.setattr(azure.time, "sleep", sleeps.append)

    job = azure._wait_for_terminal_job(
        client,
        "job-example",
        timeout_s=60,
        poll_s=2,
    )

    assert job.status == "Failed"
    assert sleeps == [2, 2]


def test_register_model_uses_direct_run_artifact_source(monkeypatch):
    import mlflow.store.artifact.runs_artifact_repo as artifact_module
    import mlflow.tracking as tracking_module

    run_id = "run-example"
    model_uri = f"runs:/{run_id}/model"
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, artifact_uri, tracking_uri=None):
            calls["repository_uri"] = artifact_uri
            calls["repository_tracking_uri"] = tracking_uri

        @staticmethod
        def parse_runs_uri(_model_uri):
            return run_id, "model"

        @staticmethod
        def get_underlying_uri(_model_uri, tracking_uri=None):
            calls["resolved_tracking_uri"] = tracking_uri
            return "azureml://artifacts/run-example/model"

        def _list_run_artifacts(self, path=None):
            calls["listed_path"] = path
            return [SimpleNamespace(path="model/MLmodel")]

    class FakeClient:
        def __init__(self, tracking_uri=None):
            calls["client_tracking_uri"] = tracking_uri

        def get_run(self, _run_id):
            return SimpleNamespace(
                data=SimpleNamespace(
                    tags={
                        "git_commit": "commit-example",
                        "data_version": "data-example",
                        "training_job_id": "job-example",
                        "image_digest": "sha256:digest-example",
                    },
                    metrics={"val_pr_auc": 0.4, "test_pr_auc": 0.5},
                    params={"seed": "1234"},
                )
            )

        def get_registered_model(self, model_name):
            calls["registered_model"] = model_name
            return SimpleNamespace(name=model_name)

        def create_model_version(self, **kwargs):
            calls["create_model_version"] = kwargs
            return SimpleNamespace(version="7")

        def get_model_version(self, _name, _version):
            return SimpleNamespace(status="READY")

        def set_model_version_tag(self, name, version, key, value):
            calls.setdefault("tags", {})[key] = value

        def update_model_version(self, name, version, description):
            calls["description"] = description

    monkeypatch.setattr(artifact_module, "RunsArtifactRepository", FakeRepository)
    monkeypatch.setattr(tracking_module, "MlflowClient", FakeClient)

    adapter = azure.AzureAdapter(SimpleNamespace())
    monkeypatch.setattr(adapter, "tracking_uri", lambda: "azureml://tracking/example")

    version = adapter.register_model(model_uri, "course-model")

    assert version == "7"
    assert calls["repository_uri"] == f"runs:/{run_id}"
    assert calls["listed_path"] == "model"
    assert calls["create_model_version"] == {
        "name": "course-model",
        "source": "azureml://artifacts/run-example/model",
        "run_id": run_id,
        "await_creation_for": 180,
    }
    assert set(calls["tags"]) == {
        "git_commit",
        "data_version",
        "mlflow_run_id",
        "training_job_id",
        "image_digest",
        "seed",
        "metric_val",
        "metric_test",
    }
