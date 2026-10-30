"""Small deterministic *simulated* dataset for the first run only."""
from datetime import timedelta
import math
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import utcnow
from .models import AppConfig, Check, Endpoint, Incident


def seed_if_needed(db: Session, enabled: bool) -> None:
    config = db.get(AppConfig, 1)
    if not config:
        config = AppConfig(id=1, sla_target=99.9, demo_seeded=False)
        db.add(config)
        db.flush()
    if not enabled or config.demo_seeded:
        db.commit()
        return
    # Never mix in examples automatically if real data already exists.
    if db.scalar(select(Endpoint.id).limit(1)) is not None:
        config.demo_seeded = True
        db.commit()
        return
    now = utcnow().replace(microsecond=0)
    base_time = now - timedelta(minutes=2)
    definitions = [
        ("API Gateway", "https://gateway.acme.test/health", 126),
        ("Authentication", "https://auth.acme.test/health", 184),
        ("Payment Service", "https://payments.acme.test/health", 220),
        ("User Service", "https://users.acme.test/health", 149),
        ("Notification API", "https://notify.acme.test/health", 164),
    ]
    endpoints = []
    for index, (name, url, baseline) in enumerate(definitions):
        endpoint = Endpoint(
            name=name, url=url, method="GET", expected_status=200,
            interval_seconds=900, timeout_seconds=10, failure_threshold=2, recovery_threshold=1,
            enabled=True, is_demo=True, archived=False, created_at=now - timedelta(days=8),
            last_checked_at=base_time, next_check_at=None,
            last_is_up=index != 2, last_status_code=503 if index == 2 else 200,
            last_response_ms=round(baseline + 20 * math.sin(index * 0.9) + 11 * math.sin(index) + (90 if index == 2 else 0), 1),
            consecutive_failures=3 if index == 2 else 0,
            consecutive_successes=0 if index == 2 else 8,
            failure_started_at=base_time - timedelta(minutes=30) if index == 2 else None,
        )
        db.add(endpoint)
        endpoints.append(endpoint)
    db.flush()
    checks = []
    # Fifteen-minute samples for seven days. Timestamps are relative; values and patterns are deterministic.
    for index, endpoint in enumerate(endpoints):
        baseline = definitions[index][2]
        for step in range(7 * 24 * 4):
            when = base_time - timedelta(minutes=15 * step)
            active_payment = index == 2 and step <= 2
            old_payment = index == 2 and 63 <= step <= 64
            old_notify = index == 4 and 172 <= step <= 173
            old_auth = index == 1 and 301 <= step <= 302
            failed = active_payment or old_payment or old_notify or old_auth
            err_type = "timeout" if old_notify else "network" if old_auth else "http_status" if failed else None
            code = None if err_type in {"timeout", "network"} else (503 if active_payment else 502 if failed else 200)
            message = ("Waktu respons melewati batas 10 detik" if old_notify else
                       "Koneksi ke host gagal" if old_auth else
                       f"HTTP {code}; status yang diharapkan adalah 200" if failed else None)
            wave = 20 * math.sin(step * 0.13 + index * 0.9) + 11 * math.sin(step * 0.43 + index)
            response = round(max(48, baseline + wave + (90 if active_payment else 0)), 1)
            if old_notify:
                response = 10000.0
            checks.append(Check(endpoint_id=endpoint.id, checked_at=when, is_up=not failed,
                                status_code=code, response_ms=response, error_type=err_type, error_message=message))
    db.add_all(checks)

    def demo_incident(idx: int, start_step: int, end_step: int | None, kind: str, code: int | None, message: str, count: int):
        ep = endpoints[idx]
        start = base_time - timedelta(minutes=15 * start_step)
        return Incident(endpoint_id=ep.id, endpoint_name=ep.name, endpoint_url=ep.url,
                        method="GET", expected_status=200, started_at=start,
                        detected_at=start + timedelta(minutes=15),
                        ended_at=(base_time - timedelta(minutes=15 * end_step)) if end_step is not None else None,
                        end_reason="recovered" if end_step is not None else None,
                        first_error_type=kind, first_error_message=message, first_status_code=code,
                        last_error_type=kind, last_error_message=message, last_status_code=code,
                        failure_count=count, notes="", is_demo=True)

    db.add_all([
        demo_incident(2, 2, None, "http_status", 503, "HTTP 503; status yang diharapkan adalah 200", 3),
        demo_incident(2, 64, 62, "http_status", 502, "HTTP 502; status yang diharapkan adalah 200", 2),
        demo_incident(4, 173, 171, "timeout", None, "Waktu respons melewati batas 10 detik", 2),
        demo_incident(1, 302, 300, "network", None, "Koneksi ke host gagal", 2),
    ])
    config.demo_seeded = True
    db.commit()
