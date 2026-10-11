"""Service contract tests without contacting a registry or cloud endpoint."""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from service import app as service

VALID = {
    "temp_c": 78.4,
    "vibration_mm_s": 3.1,
    "pressure_kpa": 315.2,
    "hours_since_service": 4200.0,
    "load_pct": 68.0,
    "ambient_humidity": 55.0,
}


class FakeModel:
    def predict_proba(self, frame):
        probabilities = np.full(len(frame), 0.25)
        return np.column_stack([1.0 - probabilities, probabilities])


@pytest.fixture()
def client(monkeypatch):
    loads: list[int] = []

    def fake_load():
        loads.append(1)
        return FakeModel()

    monkeypatch.setenv("MODEL_VERSION", "test-1")
    monkeypatch.setattr(service, "_load_model", fake_load)
    with TestClient(service.app) as test_client:
        yield test_client, loads


def test_model_is_loaded_once_and_readiness_is_distinct(client):
    test_client, loads = client
    assert test_client.get("/health").json() == {"status": "alive"}
    ready = test_client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "model_version": "test-1"}
    assert len(loads) == 1


def test_single_prediction_returns_probability_version_and_headers(client):
    test_client, _ = client
    response = test_client.post("/predict", json=VALID)
    assert response.status_code == 200
    assert response.json() == {"probability": 0.25, "model_version": "test-1"}
    assert response.headers["x-model-version"] == "test-1"
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID, "load_pct": 250.0},
        {key: value for key, value in VALID.items() if key != "temp_c"},
        {**VALID, "unknown": 1},
    ],
)
def test_malformed_input_returns_422(client, payload):
    test_client, _ = client
    assert test_client.post("/predict", json=payload).status_code == 422


def test_batch_limit_and_predictions(client):
    test_client, _ = client
    response = test_client.post("/predict/batch", json={"rows": [VALID, VALID]})
    assert response.status_code == 200
    assert response.json()["probabilities"] == [0.25, 0.25]
    assert test_client.post("/predict/batch", json={"rows": [VALID] * 101}).status_code == 422


def test_gateway_invoke_supports_single_and_batch(client):
    test_client, _ = client
    assert test_client.post("/invoke", json=VALID).json()["probability"] == 0.25
    batch = test_client.post("/invoke", json={"rows": [VALID] * 3})
    assert batch.json()["probabilities"] == [0.25, 0.25, 0.25]


def test_explicit_request_context_is_allowed_but_not_sent_to_model(client):
    test_client, _ = client
    response = test_client.post("/predict", json={**VALID, "request_context": "x" * 1024})
    assert response.status_code == 200
