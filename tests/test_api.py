import httpx
from app.monitor import is_public_address, validate_literal_target, TargetBlocked
import pytest


def test_validation_and_private_network_policy(app_client):
    app, client = app_client
    for url in ["ftp://example.com/a", "http://user:password@example.com", "https://example.com/#fragment", "not-a-url"]:
        assert client.post("/api/endpoints", json={"name":"x", "url":url}).status_code == 422
    assert client.post("/api/endpoints", json={"name":"x", "url":"https://example.com", "interval_seconds":5}).status_code == 422
    assert client.post("/api/endpoints", json={"name":"x", "url":"https://example.com", "method":"POST"}).status_code == 422
    assert not is_public_address("127.0.0.1")
    assert not is_public_address("169.254.169.254")
    assert not is_public_address("::1")
    assert not is_public_address("224.0.0.1")
    assert is_public_address("1.1.1.1")
    with pytest.raises(TargetBlocked):
        validate_literal_target("http://127.0.0.1:8000/", False)
    with pytest.raises(TargetBlocked):
        validate_literal_target("http://foo.localhost/", False)
    validate_literal_target("http://127.0.0.1:8000/", True)


def test_pause_and_archive_preserve_history_without_claiming_recovery(app_client, add_endpoint):
    app, client = app_client
    ep = add_endpoint(failure_threshold=1)
    app.state.http_transport = httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    client.post(f"/api/endpoints/{ep['id']}/check")
    incident_id = client.get("/api/incidents").json()[0]["id"]
    response = client.patch(f"/api/endpoints/{ep['id']}/enabled", json={"enabled":False})
    assert response.json()["status"] == "paused"
    assert client.post(f"/api/endpoints/{ep['id']}/check").status_code == 409
    assert client.get(f"/api/incidents/{incident_id}").json()["status"] == "open"
    assert client.delete(f"/api/endpoints/{ep['id']}").status_code == 200
    incident = client.get(f"/api/incidents/{incident_id}").json()
    assert incident["status"] == "closed" and incident["end_reason"] == "archived"
    assert client.get("/api/endpoints").json() == []
    report = client.get("/api/reports/sla?period=24h").json()
    assert report["endpoints"][0]["archived"] is True
    assert report["endpoints"][0]["failed_checks"] == 1


def test_configuration_change_closes_incident_without_recovery(app_client, add_endpoint):
    app, client = app_client
    ep = add_endpoint(failure_threshold=1)
    app.state.http_transport = httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    client.post(f"/api/endpoints/{ep['id']}/check")
    changed = client.patch(f"/api/endpoints/{ep['id']}", json={"url":"https://monitor.example/new"}).json()
    assert changed["status"] == "pending" and changed["last_checked_at"] is None
    incident = client.get("/api/incidents").json()[0]
    assert incident["status"] == "closed" and incident["end_reason"] == "config_changed"
    assert incident["endpoint_url"].endswith("/health")


def test_notes_settings_and_csv_formula_protection(app_client, add_endpoint):
    app, client = app_client
    ep = add_endpoint(name='=2+2')
    assert client.put('/api/settings', json={'sla_target':99.95}).json()['sla_target'] == 99.95
    assert client.put('/api/settings', json={'sla_target':101}).status_code == 422
    csv = client.get('/api/reports/sla.csv?period=7d')
    assert csv.status_code == 200 and csv.headers['content-type'].startswith('text/csv')
    assert "'=2+2" in csv.text
    assert client.get('/api/dashboard?period=bad').status_code == 422
    assert client.get('/api/health').json()['database'] == 'ok'
