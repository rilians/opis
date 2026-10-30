import asyncio
import csv
from contextlib import asynccontextmanager
from io import StringIO
import logging
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .analytics import incident_dict, sla_report, snapshot
from .config import Settings
from .database import Base, iso, make_engine, make_session_factory, utcnow
from .models import AlertDelivery, AppConfig, Check, Endpoint, Incident
from .monitor import CheckUnavailable, TargetBlocked, perform_check, scheduler_loop, send_webhook, validate_literal_target
from .schemas import ConfigUpdate, EnabledUpdate, EndpointCreate, EndpointUpdate, IncidentUpdate, WebhookUpdate
from .seed import seed_if_needed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# HTTPX INFO logs include full URLs, which can contain sensitive query strings.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("opis")
STATIC = Path(__file__).parent / "static"
Period = Literal["24h", "7d", "30d"]


def create_app(settings: Settings | None = None, engine=None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = engine or make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory() as db:
            seed_if_needed(db, settings.demo_data)
        scheduler = None
        if settings.scheduler_enabled:
            scheduler = asyncio.create_task(scheduler_loop(application), name="opis-scheduler")
            application.state.runtime["scheduler"] = scheduler
        logger.info("Opis started scheduler=%s demo_seed=%s", settings.scheduler_enabled, settings.demo_data)
        try:
            yield
        finally:
            if scheduler:
                scheduler.cancel()
                await asyncio.gather(scheduler, return_exceptions=True)
            tasks = list(application.state.runtime["tasks"])
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            engine.dispose()

    application = FastAPI(title="Opis API", version="1.0.0", description="API Health Monitor & Incident Reporter", lifespan=lifespan)
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.http_transport = None
    application.state.runtime = {"locks": {}, "running": set(), "tasks": set(), "scheduler": None}

    def get_db():
        with session_factory() as db:
            yield db

    def get_endpoint_or_404(db: Session, endpoint_id: int, include_archived=False) -> Endpoint:
        ep = db.get(Endpoint, endpoint_id)
        if ep is None or (ep.archived and not include_archived):
            raise HTTPException(404, "Endpoint tidak ditemukan")
        return ep

    def validate_saved_target(url: str):
        try:
            validate_literal_target(url, settings.allow_private_targets)
        except TargetBlocked as exc:
            raise HTTPException(422, str(exc)) from exc

    def endpoint_json(db: Session, endpoint_id: int, period: Period = "24h") -> dict:
        row = next((row for row in snapshot(db, period)["endpoints"] if row["id"] == endpoint_id), None)
        if not row:
            raise HTTPException(404, "Endpoint tidak ditemukan")
        return row

    @application.get("/api/health", tags=["System"])
    def health(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok", "scheduler_enabled": settings.scheduler_enabled}

    @application.get("/api/dashboard", tags=["Dashboard"])
    def dashboard(period: Period = "24h", db: Session = Depends(get_db)):
        return snapshot(db, period)

    @application.get("/api/endpoints", tags=["Endpoints"])
    def list_endpoints(period: Period = "24h", db: Session = Depends(get_db)):
        return snapshot(db, period)["endpoints"]

    @application.post("/api/endpoints", status_code=201, tags=["Endpoints"])
    def add_endpoint(payload: EndpointCreate, db: Session = Depends(get_db)):
        validate_saved_target(payload.url)
        ep = Endpoint(**payload.model_dump(), enabled=True, archived=False, is_demo=False, next_check_at=utcnow())
        db.add(ep)
        db.commit()
        db.refresh(ep)
        logger.info("endpoint_created endpoint_id=%s", ep.id)
        return endpoint_json(db, ep.id)

    @application.patch("/api/endpoints/{endpoint_id}", tags=["Endpoints"])
    def update_endpoint(endpoint_id: int, payload: EndpointUpdate, db: Session = Depends(get_db)):
        ep = get_endpoint_or_404(db, endpoint_id)
        if ep.is_demo:
            raise HTTPException(409, "Endpoint demo tidak dapat diubah. Tambahkan endpoint Anda sendiri.")
        updates = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "url" in updates:
            validate_saved_target(updates["url"])
        changes_identity = any(k in updates and updates[k] != getattr(ep, k) for k in ("url", "method", "expected_status", "timeout_seconds"))
        if changes_identity:
            open_incident = db.scalar(select(Incident).where(Incident.endpoint_id == ep.id, Incident.ended_at.is_(None)))
            if open_incident:
                open_incident.ended_at = utcnow()
                open_incident.end_reason = "config_changed"
            ep.last_checked_at, ep.last_status_code, ep.last_response_ms, ep.last_is_up = None, None, None, None
            ep.consecutive_failures, ep.consecutive_successes, ep.failure_started_at = 0, 0, None
            ep.next_check_at = utcnow()
        for key, value in updates.items():
            setattr(ep, key, value)
        db.commit()
        logger.info("endpoint_updated endpoint_id=%s", ep.id)
        return endpoint_json(db, ep.id)

    @application.patch("/api/endpoints/{endpoint_id}/enabled", tags=["Endpoints"])
    def enable_endpoint(endpoint_id: int, payload: EnabledUpdate, db: Session = Depends(get_db)):
        ep = get_endpoint_or_404(db, endpoint_id)
        if ep.is_demo:
            raise HTTPException(409, "Endpoint demo hanya berupa simulasi")
        ep.enabled = payload.enabled
        ep.next_check_at = utcnow() if payload.enabled else None
        db.commit()
        return endpoint_json(db, ep.id)

    @application.delete("/api/endpoints/{endpoint_id}", tags=["Endpoints"])
    def archive_endpoint(endpoint_id: int, db: Session = Depends(get_db)):
        ep = get_endpoint_or_404(db, endpoint_id)
        incident = db.scalar(select(Incident).where(Incident.endpoint_id == ep.id, Incident.ended_at.is_(None)))
        if incident:
            incident.ended_at, incident.end_reason = utcnow(), "archived"
        ep.archived, ep.enabled, ep.next_check_at = True, False, None
        db.commit()
        logger.info("endpoint_archived endpoint_id=%s", ep.id)
        return {"ok": True, "message": "Endpoint diarsipkan; riwayat tetap tersedia dalam laporan dan insiden."}

    @application.post("/api/endpoints/{endpoint_id}/check", tags=["Endpoints"])
    async def check_now(endpoint_id: int):
        try:
            result = await perform_check(application, endpoint_id)
        except CheckUnavailable as exc:
            raise HTTPException(409, str(exc)) from exc
        if result is None:
            raise HTTPException(409, "Konfigurasi berubah saat pemeriksaan. Coba lagi.")
        return result

    @application.get("/api/endpoints/{endpoint_id}/checks", tags=["Endpoints"])
    def endpoint_checks(endpoint_id: int, limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
        get_endpoint_or_404(db, endpoint_id, include_archived=True)
        checks = db.scalars(select(Check).where(Check.endpoint_id == endpoint_id).order_by(Check.checked_at.desc(), Check.id.desc()).limit(limit))
        return [{"id": c.id, "checked_at": iso(c.checked_at), "is_up": c.is_up, "status_code": c.status_code,
                 "response_ms": c.response_ms, "error_type": c.error_type, "error_message": c.error_message} for c in checks]

    @application.get("/api/incidents", tags=["Incidents"])
    def list_incidents(status: Literal["all", "open", "resolved", "closed"] = "all", limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
        query = select(Incident)
        if status == "open":
            query = query.where(Incident.ended_at.is_(None))
        elif status == "resolved":
            query = query.where(Incident.end_reason == "recovered")
        elif status == "closed":
            query = query.where(Incident.ended_at.is_not(None), Incident.end_reason != "recovered")
        incidents = db.scalars(query.order_by(Incident.started_at.desc(), Incident.id.desc()).limit(limit))
        return [incident_dict(i) for i in incidents]

    @application.get("/api/incidents/{incident_id}", tags=["Incidents"])
    def get_incident(incident_id: int, db: Session = Depends(get_db)):
        incident = db.get(Incident, incident_id)
        if not incident:
            raise HTTPException(404, "Insiden tidak ditemukan")
        checks = list(db.scalars(select(Check).where(Check.endpoint_id == incident.endpoint_id,
                              Check.checked_at >= incident.started_at,
                              Check.checked_at <= (incident.ended_at or utcnow())).order_by(Check.checked_at, Check.id).limit(100)))
        return {**incident_dict(incident), "checks": [{"checked_at": iso(c.checked_at), "is_up": c.is_up,
                    "status_code": c.status_code, "response_ms": c.response_ms, "error_type": c.error_type,
                    "error_message": c.error_message} for c in checks]}

    @application.patch("/api/incidents/{incident_id}", tags=["Incidents"])
    def update_incident(incident_id: int, payload: IncidentUpdate, db: Session = Depends(get_db)):
        incident = db.get(Incident, incident_id)
        if not incident:
            raise HTTPException(404, "Insiden tidak ditemukan")
        incident.notes = payload.notes
        db.commit()
        return incident_dict(incident)

    @application.get("/api/reports/sla", tags=["Reports"])
    def get_sla(period: Period = "7d", db: Session = Depends(get_db)):
        return sla_report(db, period)

    @application.get("/api/reports/sla.csv", tags=["Reports"])
    def export_sla(period: Period = "7d", db: Session = Depends(get_db)):
        report = sla_report(db, period)
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Endpoint", "URL", "Demo", "Diarsipkan", "Awal (UTC)", "Akhir (UTC)", "Berhasil", "Gagal", "Total", "Ketersediaan (%)", "Target (%)", "Durasi insiden (detik)"])
        def safe_cell(value: str):
            return "'" + value if value and value[0] in "=+-@\t\r" else value
        for ep in report["endpoints"]:
            writer.writerow([safe_cell(ep["name"]), safe_cell(ep["url"]), ep["is_demo"], ep["archived"], report["from"], report["to"],
                             ep["successful_checks"], ep["failed_checks"], ep["total_checks"], ep["uptime_percent"] if ep["uptime_percent"] is not None else "",
                             report["target_sla"], ep["incident_duration_seconds"]])
        return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="opis-sla-{period}.csv"'})

    def config_json(db: Session):
        config = db.get(AppConfig, 1)
        host = urlsplit(config.webhook_url).hostname if config.webhook_url else None
        return {"sla_target": config.sla_target, "webhook_configured": bool(config.webhook_url), "webhook_host": host,
                "scheduler_enabled": settings.scheduler_enabled, "allow_private_targets": settings.allow_private_targets,
                "demo_seed_enabled": settings.demo_data,
                "demo_count_all": len(list(db.scalars(select(Endpoint.id).where(Endpoint.is_demo.is_(True)))))}

    @application.get("/api/settings", tags=["Settings"])
    def get_settings(db: Session = Depends(get_db)):
        return config_json(db)

    @application.put("/api/settings", tags=["Settings"])
    def update_settings(payload: ConfigUpdate, db: Session = Depends(get_db)):
        config = db.get(AppConfig, 1)
        config.sla_target = payload.sla_target
        db.commit()
        return config_json(db)

    @application.put("/api/alerts/config", tags=["Alerts"])
    def update_webhook(payload: WebhookUpdate, db: Session = Depends(get_db)):
        if payload.webhook_url:
            validate_saved_target(payload.webhook_url)
        config = db.get(AppConfig, 1)
        config.webhook_url = payload.webhook_url
        db.commit()
        logger.info("webhook_configuration_updated enabled=%s", bool(payload.webhook_url))
        return config_json(db)

    @application.post("/api/alerts/test", tags=["Alerts"])
    async def test_webhook():
        delivery = await send_webhook(application, "test")
        if delivery is None:
            raise HTTPException(400, "Konfigurasikan URL webhook terlebih dahulu")
        return {"success": delivery.success, "status_code": delivery.status_code, "error_message": delivery.error_message}

    @application.get("/api/alerts", tags=["Alerts"])
    def alerts(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
        deliveries = db.scalars(select(AlertDelivery).order_by(AlertDelivery.created_at.desc(), AlertDelivery.id.desc()).limit(limit))
        return [{"id": d.id, "incident_id": d.incident_id, "endpoint_id": d.endpoint_id, "event_type": d.event_type,
                 "created_at": iso(d.created_at), "success": d.success, "status_code": d.status_code,
                 "error_message": d.error_message} for d in deliveries]

    @application.delete("/api/demo", tags=["Settings"])
    def delete_demo(db: Session = Depends(get_db)):
        count = len(list(db.scalars(select(Endpoint.id).where(Endpoint.is_demo.is_(True)))))
        db.execute(delete(Endpoint).where(Endpoint.is_demo.is_(True)))
        config = db.get(AppConfig, 1)
        config.demo_seeded = True
        db.commit()
        logger.info("demo_data_removed endpoint_count=%s", count)
        return {"ok": True, "removed_endpoints": count}

    @application.get("/", include_in_schema=False)
    def home():
        return FileResponse(STATIC / "index.html")

    application.mount("/static", StaticFiles(directory=STATIC), name="static")
    return application


app = create_app()
