from fastapi.testclient import TestClient

from service import app as service
from tests.test_service import VALID, FakeModel


def test_dashboard_signals_are_from_actual_requests(monkeypatch):
    monkeypatch.setattr(service, "_load_model", lambda: FakeModel())
    with TestClient(service.app) as client:
        client.post("/predict", json=VALID)
        client.post("/predict", json={**VALID, "temp_c": 999})
        state = client.get("/observability").json()
        assert state["request_count"] == 2
        assert state["4xx_fraction"] == 0.5
        assert state["5xx_fraction"] == 0
        assert state["latency_ms"]["p95"] > 0
        assert state["feature_mean"]["temp_c"] == VALID["temp_c"]
        assert state["feature_rows"] == 1
        assert "lab4_model_info" in client.get("/metrics").text


def test_failing_model_is_counted_as_5xx(monkeypatch):
    monkeypatch.setattr(service, "_load_model", lambda: None)
    with TestClient(service.app) as client:
        assert client.post("/predict", json=VALID).status_code == 503
        state = client.get("/observability").json()
        assert state["5xx_fraction"] == 1
