"""Azure implementation of the Lab 1 cloud portability seam."""
from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath
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
