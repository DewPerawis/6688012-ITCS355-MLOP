"""Provider-neutral deployment seam used by the Lab 3 controller scripts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CloudAdapter(ABC):
    def __init__(self, cfg) -> None:
        self.cfg = cfg

    @abstractmethod
    def push_image(self, local_tag: str) -> str:
        """Push an image and return an immutable digest reference."""

    @abstractmethod
    def download_model(self, name: str, version: str, destination: str) -> str:
        """Download an exact registered model version and return its MLflow model path."""

    @abstractmethod
    def deploy(self, model_ref: str, endpoint: str, instance: str) -> str:
        """Deploy an exact model version and return the public scoring URI."""

    @abstractmethod
    def invoke(
        self,
        endpoint: str,
        payload: dict[str, Any],
        deployment: str | None = None,
    ) -> dict[str, Any]:
        """Invoke the endpoint without exposing its key to the caller."""

    @abstractmethod
    def set_traffic(self, endpoint: str, allocations: dict[str, int]) -> dict[str, int]:
        """Apply and return a verified deployment traffic allocation."""

    @abstractmethod
    def get_model_tags(self, name: str, version: str) -> dict[str, str]:
        """Return tags for one exact registered model version."""

    @abstractmethod
    def register_model(
        self, model_uri: str, name: str, tags: dict[str, str]
    ) -> str:
        """Register a model from an immutable training-run artifact URI."""

    @abstractmethod
    def delete_deployment(
        self, endpoint: str, deployment: str, required_tags: dict[str, str]
    ) -> bool:
        """Delete one exact deployment after verifying its ownership tags."""

    @abstractmethod
    def endpoint_exists(self, endpoint: str) -> bool:
        """Return whether one exact endpoint still exists."""

    @abstractmethod
    def teardown(self, tags: dict[str, str]) -> list[str]:
        """Delete only resources whose tags match exactly."""
