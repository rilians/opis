import json
import logging
import httpx
from app.models import Check, Incident
from sqlalchemy import select


def test_failure_and_recovery_thresholds_send_exactly_one_webhook_each(app_client, add_endpoint):
    app, client = app_client
    endpoint = add_endpoint(failure_threshold=2, recovery_threshold=2)
    responses = iter([500, 503, 503, 200, 200])
    notifications = []
    def handler(request):
        if request.url.host == "hooks.example":
            notifications.append(json.loads(request.content))
            return httpx.Response(204, request=request)
        return httpx.Response(next(responses), request=request)
    app.state.http_transport = httpx.MockTransport(handler)
    assert client.put("/api/alerts/config", json={"webhook_url":"https://hooks.example/secret-token"}).status_code == 200
    settings = client.get("/api/settings").json()
    assert settings["webhook_configured"] and settings["webhook_host"] == "hooks.example"
    assert "secret-token" not in str(settings)

    def check():
        response = client.post(f"/api/endpoints/{endpoint['id']}/check")
        assert response.status_code == 200, response.text
        return response.json()

    assert check()["status_code"] == 500
    assert client.get("/api/incidents").json() == []
    assert client.get("/api/endpoints").json()[0]["status"] == "degraded"
    assert check()["status_code"] == 503
    incident = client.get("/api/incidents").json()[0]
    assert incident["status"] == "open"
    assert incident["failure_count"] == 2
    assert incident["first_status_code"] == 500  # preserve first failure, not the trigger check
    assert incident["last_status_code"] == 503
    assert "Periksa log" in incident["investigation"]  # a suggestion, not an asserted cause
    check()  # later failures do not send another open alert
    assert client.get("/api/incidents").json()[0]["failure_count"] == 3
    check()
    assert client.get("/api/incidents").json()[0]["status"] == "open"
    assert client.get("/api/endpoints").json()[0]["status"] == "down"
    check()
    final = client.get("/api/incidents").json()[0]
    assert final["status"] == "resolved" and final["end_reason"] == "recovered"
    assert [n["event"] for n in notifications] == ["incident.opened", "incident.resolved"]
    assert all(n["incident"]["endpoint_id"] == endpoint["id"] for n in notifications)
    deliveries = client.get("/api/alerts").json()
    assert len(deliveries) == 2 and all(d["success"] for d in deliveries)
    detail = client.get(f"/api/incidents/{final['id']}").json()
    assert len(detail["checks"]) == 5
    assert client.patch(f"/api/incidents/{final['id']}", json={"notes":"Penyebab diverifikasi di gateway."}).json()["notes"] == "Penyebab diverifikasi di gateway."


def test_timeout_network_failures_and_logging(app_client, add_endpoint, caplog):
    app, client = app_client
    ep = add_endpoint(failure_threshold=1)
    errors = iter([httpx.ReadTimeout("timeout"), httpx.ConnectError("connection refused")])
    def handler(request):
        raise next(errors)
    app.state.http_transport = httpx.MockTransport(handler)
    with caplog.at_level(logging.WARNING, logger="opis.monitor"):
        first = client.post(f"/api/endpoints/{ep['id']}/check").json()
        second = client.post(f"/api/endpoints/{ep['id']}/check").json()
    assert first["error_type"] == "timeout" and first["status_code"] is None
    assert second["error_type"] == "network"
    inc = client.get("/api/incidents").json()[0]
    assert inc["first_error_type"] == "timeout" and inc["last_error_type"] == "network"
    assert inc["failure_count"] == 2
    assert "check_failed" in caplog.text and "incident_opened" in caplog.text
    assert "monitor.example" not in caplog.text


def test_redirect_is_not_followed(app_client, add_endpoint):
    app, client = app_client
    ep = add_endpoint(failure_threshold=1)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location":"https://another.example/"}, request=request)
    app.state.http_transport = httpx.MockTransport(handler)
    check = client.post(f"/api/endpoints/{ep['id']}/check").json()
    assert not check["is_up"] and check["status_code"] == 302
    assert len(calls) == 1


def test_webhook_failure_is_recorded_without_losing_check(app_client, add_endpoint):
    app, client = app_client
    ep = add_endpoint(failure_threshold=1)
    def handler(request):
        return httpx.Response(500 if request.url.host == "hooks.example" else 503, request=request)
    app.state.http_transport = httpx.MockTransport(handler)
    client.put("/api/alerts/config", json={"webhook_url":"https://hooks.example/events"})
    result = client.post(f"/api/endpoints/{ep['id']}/check")
    assert result.status_code == 200 and not result.json()["is_up"]
    delivery = client.get("/api/alerts").json()[0]
    assert not delivery["success"] and delivery["status_code"] == 500
    assert "HTTP 500" in delivery["error_message"]
    assert len(client.get(f"/api/endpoints/{ep['id']}/checks").json()) == 1
    assert client.get("/api/incidents").json()[0]["status"] == "open"


def test_http_head_and_custom_expected_status(app_client, add_endpoint):
    app, client = app_client
    ep = add_endpoint(method="HEAD", expected_status=204)
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(204, request=request)
    app.state.http_transport = httpx.MockTransport(handler)
    check = client.post(f"/api/endpoints/{ep['id']}/check").json()
    assert calls == ["HEAD"] and check["is_up"] and check["status_code"] == 204
