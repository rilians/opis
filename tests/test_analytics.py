from datetime import datetime, timedelta, timezone
from app.analytics import snapshot, sla_report
from app.models import Check, Endpoint, Incident


def test_sample_based_sla_and_clipped_incident_duration(app_client):
    app, client = app_client
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    with app.state.session_factory() as db:
        first = Endpoint(name="A", url="https://a.example/", enabled=True, is_demo=False, archived=False,
                         created_at=now-timedelta(days=2), last_checked_at=now-timedelta(hours=1), last_is_up=True)
        second = Endpoint(name="B", url="https://b.example/", enabled=True, is_demo=False, archived=False,
                          created_at=now-timedelta(days=2), last_checked_at=now-timedelta(hours=1), last_is_up=True)
        empty = Endpoint(name="C", url="https://c.example/", enabled=True, is_demo=False, archived=False,
                         created_at=now-timedelta(days=2))
        db.add_all([first, second, empty]); db.flush()
        for hour, success in [(1,True), (2,True), (3,False), (4,True)]:
            db.add(Check(endpoint_id=first.id, checked_at=now-timedelta(hours=hour), is_up=success,
                         status_code=200 if success else 503, response_ms=100.0))
        db.add(Check(endpoint_id=second.id, checked_at=now-timedelta(hours=1), is_up=True, status_code=200, response_ms=200.0))
        db.add(Incident(endpoint_id=first.id, endpoint_name="A", endpoint_url=first.url, method="GET", expected_status=200,
                        started_at=now-timedelta(hours=25), detected_at=now-timedelta(hours=24, minutes=45),
                        ended_at=now-timedelta(hours=23), end_reason="recovered", first_error_type="http_status",
                        first_error_message="HTTP 503", first_status_code=503, failure_count=1, notes="", is_demo=False))
        db.commit()
        data = snapshot(db, "24h", now=now)
        assert data["total_checks"] == 5 and data["successful_checks"] == 4
        assert data["uptime_percent"] == 80.0  # weighted by checks, not a mean of endpoint percentages
        assert data["avg_response_ms"] == 120.0
        rows = {item["name"]: item for item in data["endpoints"]}
        assert rows["A"]["uptime_percent"] == 75.0
        assert rows["B"]["uptime_percent"] == 100.0
        assert rows["C"]["uptime_percent"] is None  # no samples is not 100%
        report = sla_report(db, "24h", now=now)
        reported = {item["name"]: item for item in report["endpoints"]}
        assert reported["A"]["incident_duration_seconds"] == 3600  # clipped at period start
        assert reported["A"]["meets_target"] is False
        assert reported["C"]["meets_target"] is None
        assert "berbasis sampel" in report["methodology"]


def test_target_comparison_uses_unrounded_samples(app_client):
    from app.models import AppConfig
    app, _ = app_client
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    with app.state.session_factory() as db:
        db.get(AppConfig, 1).sla_target = 66.667
        ep = Endpoint(name='Boundary', url='https://boundary.example', enabled=True, is_demo=False, archived=False, created_at=now-timedelta(days=1))
        db.add(ep); db.flush()
        for i, success in enumerate([True, True, False]):
            db.add(Check(endpoint_id=ep.id, checked_at=now-timedelta(minutes=i+1), is_up=success, response_ms=50))
        db.commit()
        result = sla_report(db, '24h', now=now)
        assert result['uptime_percent'] == 66.667  # displayed rounded
        assert result['meets_target'] is False  # true 2/3 is below 66.667
        assert result['endpoints'][0]['meets_target'] is False
