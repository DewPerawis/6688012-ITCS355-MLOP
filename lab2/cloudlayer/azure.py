"""Azure implementation of the cloud portability seam through Lab 2."""
from __future__ import annotations

import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from cloudlayer.base import CloudAdapter


def _blob_location(uri: str) -> tuple[str, str, str]:
    """Return account URL, container, and blob prefix/name from an HTTPS Blob URI."""
    parsed = urlsplit(uri)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Azure Blob URI must use HTTPS")
    if not parsed.hostname.endswith(".blob.core.windows.net"):
        raise ValueError("Azure Blob URI must use a blob.core.windows.net host")
    if parsed.query or parsed.fragment:
        raise ValueError("Azure Blob URI must not contain a query string or fragment")

    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not path_parts:
        raise ValueError("Azure Blob URI must include a container")
    account_url = f"https://{parsed.hostname}"
    return account_url, path_parts[0], "/".join(path_parts[1:])


def _safe_blob_key(key: str) -> str:
    candidate = PurePosixPath(key.replace("\\", "/"))
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise ValueError(f"unsafe blob key: {key!r}")
    return candidate.as_posix()


def _run_output(args: list[str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout.strip()


class AzureAdapter(CloudAdapter):
    def _ml_client(self):
        if not self.cfg.azure_subscription_id:
            raise RuntimeError("AZURE_SUBSCRIPTION_ID is required for Azure ML operations")
        if not self.cfg.azure_resource_group or not self.cfg.azureml_workspace:
            raise RuntimeError("AZURE_RESOURCE_GROUP and AZUREML_WORKSPACE are required")

        from azure.ai.ml import MLClient

        return MLClient(
            DefaultAzureCredential(),
            self.cfg.azure_subscription_id,
            self.cfg.azure_resource_group,
            self.cfg.azureml_workspace,
        )

    def tracking_uri(self) -> str:
        workspace = self._ml_client().workspaces.get(self.cfg.azureml_workspace)
        if not workspace.mlflow_tracking_uri:
            raise RuntimeError("Azure ML workspace returned no MLflow tracking URI")
        return workspace.mlflow_tracking_uri

    def upload(self, local_path: str, key: str) -> str:
        source = Path(local_path)
        if not source.is_file():
            raise FileNotFoundError(f"upload source is not a file: {source}")

        account_url, container, prefix = _blob_location(self.cfg.blob_uri)
        blob_name = "/".join(part for part in (prefix, _safe_blob_key(key)) if part)
        credential = DefaultAzureCredential()
        try:
            with BlobServiceClient(account_url, credential=credential) as service:
                blob = service.get_blob_client(container=container, blob=blob_name)
                with source.open("rb") as stream:
                    blob.upload_blob(stream, overwrite=True)
                return blob.url
        finally:
            credential.close()

    def download(self, uri: str, local_path: str) -> None:
        account_url, container, blob_name = _blob_location(uri)
        if not blob_name:
            raise ValueError("Azure Blob object URI must include a blob name")

        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        credential = DefaultAzureCredential()
        try:
            with BlobServiceClient(account_url, credential=credential) as service:
                blob = service.get_blob_client(container=container, blob=blob_name)
                with destination.open("wb") as stream:
                    blob.download_blob().readinto(stream)
        finally:
            credential.close()

    def push_image(self, local_tag: str) -> str:
        registry = self.cfg.container_registry.strip().rstrip("/")
        if "/" not in registry:
            raise ValueError("CONTAINER_REGISTRY must contain login-server/repository")
        login_server, repository = registry.split("/", 1)
        if not login_server.endswith(".azurecr.io") or not repository:
            raise ValueError("CONTAINER_REGISTRY must be an Azure login server and repository")

        local_name = local_tag.rsplit("/", 1)[-1]
        tag = local_name.rsplit(":", 1)[1] if ":" in local_name else "latest"
        remote_tag = f"{login_server}/{repository}:{tag}"

        query = f"[?loginServer=='{login_server}'].name | [0]"
        registry_name = _run_output(["az", "acr", "list", "--query", query, "-o", "tsv"])
        if not registry_name:
            raise RuntimeError(f"no accessible ACR matches login server {login_server}")

        subprocess.run(["az", "acr", "login", "--name", registry_name], check=True)
        subprocess.run(["docker", "tag", local_tag, remote_tag], check=True)
        subprocess.run(["docker", "push", remote_tag], check=True)

        digest = _run_output([
            "az", "acr", "repository", "show",
            "--name", registry_name,
            "--image", f"{repository}:{tag}",
            "--query", "digest",
            "-o", "tsv",
        ])
        if not digest.startswith("sha256:"):
            raise RuntimeError(f"ACR returned an invalid digest: {digest!r}")
        return f"{login_server}/{repository}@{digest}"

    def submit_training(self, image_uri: str, args: dict[str, Any]) -> str:
        """Submit the Lab 2 container as an Azure ML command job.

        Data is a private Blob input accessed with the submitter's Entra identity. The
        checkpoint/report output is an rw-mounted datastore path reused by a resumed job.
        """
        if "@sha256:" not in image_uri:
            raise ValueError("managed training image must be digest-pinned")
        required = {"data_uri", "output_uri", "data_version", "experiment", "study_id"}
        missing = sorted(required - args.keys())
        if missing:
            raise ValueError(f"missing training arguments: {', '.join(missing)}")

        from azure.ai.ml import Input, Output, command
        from azure.ai.ml.entities import CommandJobLimits, Environment, UserIdentityConfiguration

        trials = int(args.get("trials", 12))
        budget_thb = float(args.get("budget_thb", 150.0))
        seed_repeats = int(args.get("seed_repeats", 5))
        interrupt_after = int(args.get("interrupt_after", 0))
        if trials < 12:
            raise ValueError("Lab 2 requires at least 12 trials")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        job_name = str(args.get("job_name") or f"lab2-{timestamp}-{args['study_id'][-8:]}")
        command_parts = [
            "python", "-m", "src.tune",
            "--trials", str(trials),
            "--budget-thb", str(budget_thb),
            "--seed-repeats", str(seed_repeats),
            "--instance", self.cfg.training_instance,
            "--experiment", str(args["experiment"]),
            "--data-path", "${{inputs.training_data}}",
            "--checkpoint", "${{outputs.study}}/tune_checkpoint.json",
            "--summary-out", "${{outputs.study}}/lab2-study.json",
        ]
        if interrupt_after:
            command_parts.extend(["--interrupt-after", str(interrupt_after)])
        shell_command = " ".join(
            part if part.startswith("${{") else shlex.quote(part) for part in command_parts
        )

        job = command(
            name=job_name,
            display_name=job_name,
            experiment_name=str(args["experiment"]),
            command=shell_command,
            environment=Environment(image=image_uri),
            compute=self.cfg.training_target,
            inputs={
                "training_data": Input(
                    type="uri_file", path=str(args["data_uri"]), mode="download"
                )
            },
            outputs={
                "study": Output(
                    type="uri_folder", path=str(args["output_uri"]), mode="rw_mount"
                )
            },
            identity=UserIdentityConfiguration(),
            environment_variables={
                "GIT_COMMIT": str(args.get("git_commit", "unknown")),
                "DATA_VERSION": str(args["data_version"]),
                "TRAINING_JOB_ID": job_name,
                "IMAGE_DIGEST": image_uri.split("@", 1)[1],
                "PYTHONHASHSEED": str(args.get("seed", 20260101)),
            },
            tags={**self.cfg.tags(2), "study": str(args["study_id"])},
            limits=CommandJobLimits(timeout=int(args.get("timeout_s", 7200))),
        )
        created = self._ml_client().jobs.create_or_update(job)
        return created.name

    def wait_training(self, job_id: str) -> dict[str, Any]:
        client = self._ml_client()
        stream_error = None
        try:
            client.jobs.stream(job_id)
        except Exception as exc:  # Azure raises after streaming a failed user command.
            stream_error = f"{type(exc).__name__}: {exc}"
        job = client.jobs.get(job_id)
        return {
            "job_id": job.name,
            "status": job.status,
            "studio_url": job.studio_url,
            "error": str(job.error) if getattr(job, "error", None) else None,
            "stream_error": stream_error,
        }

    def register_model(self, model_uri: str, name: str) -> str:
        """Register an MLflow model and attach all eight required lineage fields."""
        if not model_uri.startswith("runs:/"):
            raise ValueError("model_uri must identify an MLflow run artifact: runs:/...")

        import mlflow
        from mlflow.tracking import MlflowClient

        tracking_uri = self.tracking_uri()
        mlflow.set_tracking_uri(tracking_uri)
        run_id = model_uri.removeprefix("runs:/").split("/", 1)[0]
        client = MlflowClient(tracking_uri=tracking_uri)
        run = client.get_run(run_id)
        tags = run.data.tags
        metrics = run.data.metrics
        params = run.data.params
        lineage = {
            "git_commit": tags.get("git_commit", ""),
            "data_version": tags.get("data_version", ""),
            "mlflow_run_id": run_id,
            "training_job_id": tags.get("training_job_id", ""),
            "image_digest": tags.get("image_digest", ""),
            "seed": params.get("seed", ""),
            "metric_val": str(metrics.get("val_pr_auc", "")),
            "metric_test": str(metrics.get("test_pr_auc", "")),
        }
        missing = [key for key, value in lineage.items() if value in (None, "", "unknown")]
        if missing:
            raise ValueError(f"refusing to register incomplete lineage: {', '.join(missing)}")

        registered = mlflow.register_model(model_uri, name)
        version = str(registered.version)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            current = client.get_model_version(name, version)
            if str(current.status).upper() == "READY":
                break
            time.sleep(2)
        else:
            raise TimeoutError(f"model {name} version {version} was not READY after 180 s")

        for key, value in lineage.items():
            client.set_model_version_tag(name, version, key, str(value))
        client.update_model_version(
            name,
            version,
            description=(
                "ITCS355 Lab 2 candidate selected by a validation PR-AUC/cost rule; "
                "held-out test metrics were not used for selection."
            ),
        )
        return version

    def promote_model(self, name: str, version: str, stage: str = "Staging") -> None:
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=self.tracking_uri())
        client.transition_model_version_stage(
            name=name,
            version=version,
            stage=stage,
            archive_existing_versions=False,
        )
        client.set_model_version_tag(name, version, "promotion_stage", stage)

    def teardown(self, tags: dict[str, str]) -> list[str]:
        """Remove Lab 2 compute and archive its jobs; retain workspace and models.

        Azure ML command jobs have an archive operation rather than a destructive delete.
        The compute target is deleted only after every requested tag matches, preventing a
        broad course-level cleanup from touching unrelated resources.
        """
        if tags.get("lab") != "2":
            raise ValueError("this Lab 2 teardown only accepts tags with lab=2")

        from azure.core.exceptions import ResourceNotFoundError

        client = self._ml_client()
        affected: list[str] = []

        try:
            compute = client.compute.get(self.cfg.training_target)
        except ResourceNotFoundError:
            compute = None
        if compute is not None:
            compute_tags = getattr(compute, "tags", {}) or {}
            if not all(compute_tags.get(key) == value for key, value in tags.items()):
                raise RuntimeError(
                    f"refusing to delete compute {compute.name!r}: tags do not match {tags}"
                )
            client.compute.begin_delete(compute.name).result()
            affected.append(f"deleted compute:{compute.name}")

        for job in client.jobs.list():
            job_tags = getattr(job, "tags", {}) or {}
            if all(job_tags.get(key) == value for key, value in tags.items()):
                client.jobs.archive(job.name)
                affected.append(f"archived job:{job.name}")

        return affected
