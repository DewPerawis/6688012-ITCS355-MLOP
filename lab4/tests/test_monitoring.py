import pytest

from cloudlayer import observability
from monitoring.alerts import deliver


def test_recent_input_query_scopes_endpoint_version_and_window(monkeypatch):
    queries = []
    monkeypatch.setattr(observability, "query_logs", lambda workspace, query, timespan:
                        queries.append(query) or [])
    observability.recent_inputs("unused", "itcs355-6688012-lab4", "1")
    assert 'e.endpoint == "itcs355-6688012-lab4"' in queries[0]
    assert 'e.model_version) == "1"' in queries[0]
    assert "top 500 by EventTime desc" in queries[0]


def test_unsafe_identifiers_do_not_reach_query(monkeypatch):
    monkeypatch.setattr(observability, "query_logs", lambda *args: pytest.fail("network reached"))
    with pytest.raises(ValueError):
        observability.recent_inputs("unused", 'bad" | union', "1")


def test_webhook_transport_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        deliver("http://example.invalid", "test")
