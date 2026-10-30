from collections import defaultdict
from datetime import timedelta
from typing import Iterable
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import aware, iso, utcnow
from .models import AppConfig, Check, Endpoint, Incident

PERIODS = {
    "24h": (timedelta(hours=24), 24),
    "7d": (timedelta(days=7), 28),
    "30d": (timedelta(days=30), 30),
}


def pct(success: int, total: int) -> float | None:
    return round(success * 100 / total, 3) if total else None


def mean(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 1) if present else None


def endpoint_status(ep: Endpoint, has_open_incident: bool) -> str:
    if not ep.enabled:
        return "paused"
    if has_open_incident:
        return "down"
    if ep.last_is_up is None:
        return "pending"
    return "up" if ep.last_is_up else "degraded"


def incident_status(incident: Incident) -> str:
    return "open" if incident.ended_at is None else "resolved" if incident.end_reason == "recovered" else "closed"


def incident_dict(incident: Incident, now=None) -> dict:
    now = now or utcnow()
    end = aware(incident.ended_at) or now
    start = aware(incident.started_at)
    status = incident_status(incident)
    error_labels = {"http_status": "Status HTTP tidak sesuai", "timeout": "Batas waktu terlampaui",
                    "network": "Kesalahan koneksi", "security": "Tujuan diblokir", "unexpected": "Kesalahan pemeriksaan"}
    suggestions = {
        "http_status": "Periksa log aplikasi dan gateway di sekitar waktu kejadian; bandingkan respons dengan status yang diharapkan.",
        "timeout": "Periksa latensi layanan, beban, koneksi, serta batas waktu di gateway atau upstream.",
        "network": "Periksa DNS, konektivitas, TLS, firewall, dan ketersediaan host dari mesin pemantau.",
        "security": "Periksa kebijakan alamat tujuan dan konfigurasi jaringan pemantau.",
        "unexpected": "Periksa log Opis dan layanan terkait pada waktu kejadian.",
    }
    kind = incident.first_error_type or "unexpected"
    observed = incident.first_error_message or error_labels.get(kind, "Kesalahan pemeriksaan")
    return {
        "id": incident.id, "endpoint_id": incident.endpoint_id,
        "endpoint_name": incident.endpoint_name, "endpoint_url": incident.endpoint_url,
        "method": incident.method, "expected_status": incident.expected_status,
        "status": status, "started_at": iso(incident.started_at), "detected_at": iso(incident.detected_at),
        "ended_at": iso(incident.ended_at), "end_reason": incident.end_reason,
        "duration_seconds": max(0, int((end - start).total_seconds())),
        "first_error_type": incident.first_error_type, "first_error_message": incident.first_error_message,
        "first_status_code": incident.first_status_code, "last_error_type": incident.last_error_type,
        "last_error_message": incident.last_error_message, "last_status_code": incident.last_status_code,
        "failure_count": incident.failure_count, "notes": incident.notes, "is_demo": incident.is_demo,
        "title": error_labels.get(kind, "Kesalahan pemeriksaan"),
        "summary": f"{incident.endpoint_name}: {observed}. Tercatat {incident.failure_count} pemeriksaan gagal selama insiden.",
        "investigation": suggestions.get(kind, suggestions["unexpected"]),
    }


def endpoint_dict(ep: Endpoint, checks: list[Check], open_incident: Incident | None, start, end, bins: int) -> dict:
    duration = (end - start).total_seconds()
    segments: list[list[bool]] = [[] for _ in range(bins)]
    for check in checks:
        index = int((aware(check.checked_at) - start).total_seconds() / duration * bins)
        index = max(0, min(bins - 1, index))
        segments[index].append(check.is_up)
    states = ["empty" if not group else "up" if all(group) else "down" if not any(group) else "degraded" for group in segments]
    successful = sum(1 for c in checks if c.is_up)
    return {
        "id": ep.id, "name": ep.name, "url": ep.url, "method": ep.method,
        "expected_status": ep.expected_status, "interval_seconds": ep.interval_seconds,
        "timeout_seconds": ep.timeout_seconds, "failure_threshold": ep.failure_threshold,
        "recovery_threshold": ep.recovery_threshold, "enabled": ep.enabled, "is_demo": ep.is_demo,
        "archived": ep.archived, "created_at": iso(ep.created_at), "last_checked_at": iso(ep.last_checked_at),
        "next_check_at": iso(ep.next_check_at), "last_status_code": ep.last_status_code,
        "last_response_ms": ep.last_response_ms, "consecutive_failures": ep.consecutive_failures,
        "consecutive_successes": ep.consecutive_successes,
        "status": endpoint_status(ep, open_incident is not None),
        "incident_id": open_incident.id if open_incident else None,
        "uptime_percent": pct(successful, len(checks)), "total_checks": len(checks),
        "successful_checks": successful, "avg_response_ms": mean(c.response_ms for c in checks),
        "segments": states,
    }


def snapshot(db: Session, period: str = "24h", now=None, include_archived: bool = False) -> dict:
    now = now or utcnow()
    duration, bin_count = PERIODS[period]
    start = now - duration
    query = select(Endpoint).order_by(Endpoint.created_at, Endpoint.id)
    if not include_archived:
        query = query.where(Endpoint.archived.is_(False))
    endpoints = list(db.scalars(query))
    ids = [ep.id for ep in endpoints]
    checks = list(db.scalars(select(Check).where(Check.endpoint_id.in_(ids), Check.checked_at >= start, Check.checked_at <= now).order_by(Check.checked_at))) if ids else []
    incidents = list(db.scalars(select(Incident).where(Incident.endpoint_id.in_(ids), Incident.started_at <= now,
                        (Incident.ended_at.is_(None)) | (Incident.ended_at >= start)).order_by(Incident.started_at.desc()))) if ids else []
    check_map: dict[int, list[Check]] = defaultdict(list)
    for check in checks:
        check_map[check.endpoint_id].append(check)
    open_map = {inc.endpoint_id: inc for inc in incidents if inc.ended_at is None}
    ep_rows = [endpoint_dict(ep, check_map[ep.id], open_map.get(ep.id), start, now, bin_count) for ep in endpoints]
    chart = []
    bucket_seconds = duration.total_seconds() / bin_count
    buckets: list[list[Check]] = [[] for _ in range(bin_count)]
    for check in checks:
        position = int((aware(check.checked_at) - start).total_seconds() / bucket_seconds)
        buckets[max(0, min(bin_count - 1, position))].append(check)
    for i, bucket in enumerate(buckets):
        chart.append({"at": iso(start + timedelta(seconds=i * bucket_seconds)),
                      "response_ms": mean(c.response_ms for c in bucket),
                      "uptime_percent": pct(sum(1 for c in bucket if c.is_up), len(bucket)),
                      "checks": len(bucket)})
    config = db.get(AppConfig, 1)
    target = config.sla_target if config else 99.9
    successful_count = sum(1 for c in checks if c.is_up)
    for row in ep_rows:
        row["meets_target"] = None if not row["total_checks"] else (100 * row["successful_checks"] / row["total_checks"] >= target)
    statuses = {key: sum(1 for e in ep_rows if e["status"] == key) for key in ["up", "down", "degraded", "pending", "paused"]}
    return {
        "period": period, "from": iso(start), "to": iso(now), "target_sla": target,
        "meets_target": None if not checks else (100 * successful_count / len(checks) >= target),
        "total_endpoints": len(ep_rows), "demo_count": sum(e["is_demo"] for e in ep_rows),
        "active_incidents": len(open_map), "status_counts": statuses,
        "uptime_percent": pct(successful_count, len(checks)),
        "total_checks": len(checks), "successful_checks": successful_count,
        "avg_response_ms": mean(c.response_ms for c in checks),
        "endpoints": ep_rows, "chart": chart,
        "recent_incidents": [incident_dict(i, now) for i in incidents[:6]],
    }


def sla_report(db: Session, period: str, now=None) -> dict:
    now = now or utcnow()
    data = snapshot(db, period, now, include_archived=True)
    start = now - PERIODS[period][0]
    rows = []
    for ep in data["endpoints"]:
        incidents = list(db.scalars(select(Incident).where(Incident.endpoint_id == ep["id"], Incident.started_at <= now,
                                (Incident.ended_at.is_(None)) | (Incident.ended_at >= start))))
        seconds = sum(max(0, (min(aware(i.ended_at) or now, now) - max(aware(i.started_at), start)).total_seconds()) for i in incidents)
        rows.append({**ep, "failed_checks": ep["total_checks"] - ep["successful_checks"],
                     "incident_count": len(incidents), "incident_duration_seconds": int(seconds),
                     "meets_target": ep["meets_target"]})
    return {**data, "endpoints": rows,
            "methodology": "Ketersediaan = pemeriksaan berhasil ÷ seluruh pemeriksaan pada periode. Ini berbasis sampel, bukan durasi. Target dibandingkan sebelum pembulatan tampilan. Periode tanpa data tidak dianggap 100%. Durasi insiden adalah estimasi dari pemeriksaan gagal pertama hingga pemulihan atau penutupan."}
