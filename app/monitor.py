import asyncio
import ipaddress
import logging
import socket
import time
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from .analytics import incident_dict
from .database import aware, iso, utcnow
from .models import AlertDelivery, AppConfig, Check, Endpoint, Incident

logger = logging.getLogger("opis.monitor")


class TargetBlocked(ValueError):
    pass


class CheckUnavailable(ValueError):
    pass


def is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
        return ip.is_global and not ip.is_multicast and not ip.is_unspecified and not ip.is_reserved
    except ValueError:
        return False


def validate_literal_target(url: str, allow_private: bool) -> None:
    """Quick validation on save; full DNS validation is done before each request."""
    if allow_private:
        return
    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise TargetBlocked("Alamat lokal/privat diblokir. Aktifkan OPIS_ALLOW_PRIVATE_TARGETS hanya pada jaringan tepercaya.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return
    if not is_public_address(host):
        raise TargetBlocked("Alamat lokal/privat diblokir. Aktifkan OPIS_ALLOW_PRIVATE_TARGETS hanya pada jaringan tepercaya.")


async def validate_target(url: str, allow_private: bool) -> None:
    if allow_private:
        return
    validate_literal_target(url, allow_private)
    parsed = urlsplit(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not records or any(not is_public_address(record[4][0]) for record in records):
        raise TargetBlocked("Host mengarah ke alamat lokal/privat dan diblokir oleh kebijakan keamanan.")


def _runtime(app):
    return app.state.runtime


async def send_webhook(app, event_type: str, incident: dict | None = None) -> AlertDelivery | None:
    """Send a best-effort webhook. A failed delivery is recorded, not raised into monitoring."""
    with app.state.session_factory() as db:
        config = db.get(AppConfig, 1)
        url = config.webhook_url if config else None
    if not url:
        return None
    payload = {"event": event_type, "source": "opis", "sent_at": iso(utcnow()), "incident": incident}
    status_code = None
    error = None
    success = False
    try:
        async with asyncio.timeout(5.0):
            await validate_target(url, app.state.settings.allow_private_targets)
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False,
                                         transport=getattr(app.state, "http_transport", None)) as client:
                async with client.stream("POST", url, json=payload) as response:
                    status_code = response.status_code
                    success = 200 <= status_code < 300
                    if not success:
                        error = f"Webhook merespons HTTP {status_code}"
    except TargetBlocked:
        error = "Tujuan webhook diblokir oleh kebijakan jaringan"
    except (httpx.TimeoutException, asyncio.TimeoutError):
        error = "Pengiriman webhook melewati batas waktu 5 detik"
    except (httpx.RequestError, OSError) as exc:
        error = f"Koneksi webhook gagal ({type(exc).__name__})"
    except Exception:
        logger.exception("Unexpected webhook delivery error")
        error = "Kesalahan internal saat mengirim webhook"
    with app.state.session_factory() as db:
        delivery = AlertDelivery(incident_id=incident.get("id") if incident else None,
                                 endpoint_id=incident.get("endpoint_id") if incident else None,
                                 event_type=event_type, success=success, status_code=status_code,
                                 error_message=error, created_at=utcnow())
        # An incident can be removed while a webhook is in flight; do not lose the delivery record.
        if delivery.incident_id is not None and db.get(Incident, delivery.incident_id) is None:
            delivery.incident_id = None
        if delivery.endpoint_id is not None and db.get(Endpoint, delivery.endpoint_id) is None:
            delivery.endpoint_id = None
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
    if not success:
        logger.warning("webhook_delivery_failed event=%s status=%s error=%s", event_type, status_code, error)
    return delivery


async def perform_check(app, endpoint_id: int, only_if_due: bool = False) -> dict | None:
    runtime = _runtime(app)
    lock = runtime["locks"].setdefault(endpoint_id, asyncio.Lock())
    async with lock:
        with app.state.session_factory() as db:
            ep = db.get(Endpoint, endpoint_id)
            if not ep or ep.archived:
                raise CheckUnavailable("Endpoint tidak ditemukan")
            if ep.is_demo:
                raise CheckUnavailable("Endpoint demo hanya simulasi dan tidak mengirim permintaan nyata")
            if not ep.enabled:
                raise CheckUnavailable("Endpoint sedang dijeda")
            if only_if_due and ep.next_check_at and aware(ep.next_check_at) > utcnow():
                return None
            # Snapshot avoids using a database session during network I/O.
            monitor = {"id": ep.id, "name": ep.name, "url": ep.url, "method": ep.method,
                       "expected_status": ep.expected_status, "timeout_seconds": ep.timeout_seconds}

        started = time.perf_counter()
        is_up, status_code, error_type, error_message = False, None, None, None
        try:
            async with asyncio.timeout(float(monitor["timeout_seconds"])):
                await validate_target(monitor["url"], app.state.settings.allow_private_targets)
                async with httpx.AsyncClient(timeout=float(monitor["timeout_seconds"]), follow_redirects=False,
                                             trust_env=False, transport=getattr(app.state, "http_transport", None)) as client:
                    # Streaming closes after response headers and does not download an unbounded body.
                    async with client.stream(monitor["method"], monitor["url"]) as response:
                        status_code = response.status_code
                        is_up = status_code == monitor["expected_status"]
                        if not is_up:
                            error_type = "http_status"
                            error_message = f"HTTP {status_code}; status yang diharapkan adalah {monitor['expected_status']}"
        except TargetBlocked as exc:
            error_type, error_message = "security", str(exc)
        except (httpx.TimeoutException, asyncio.TimeoutError):
            error_type, error_message = "timeout", f"Waktu respons melewati batas {monitor['timeout_seconds']} detik"
        except (httpx.RequestError, OSError) as exc:
            error_type, error_message = "network", f"Koneksi ke host gagal ({type(exc).__name__})"
        except Exception:
            logger.exception("Unexpected monitor error endpoint_id=%s", endpoint_id)
            error_type, error_message = "unexpected", "Kesalahan internal saat memeriksa endpoint"
        response_ms = round((time.perf_counter() - started) * 1000, 1)
        checked_at = utcnow()
        notify = None
        with app.state.session_factory() as db:
            ep = db.get(Endpoint, endpoint_id)
            if not ep or ep.archived or not ep.enabled or any(getattr(ep, key) != monitor[key] for key in ("url", "method", "expected_status", "timeout_seconds")):
                logger.info("check_discarded endpoint_id=%s reason=configuration_changed", endpoint_id)
                return None
            ep.last_checked_at = checked_at
            ep.next_check_at = checked_at + timedelta(seconds=ep.interval_seconds)
            ep.last_is_up, ep.last_status_code, ep.last_response_ms = is_up, status_code, response_ms
            check = Check(endpoint_id=ep.id, checked_at=checked_at, is_up=is_up, status_code=status_code,
                          response_ms=response_ms, error_type=error_type, error_message=error_message)
            db.add(check)
            db.flush()
            incident = db.scalar(select(Incident).where(Incident.endpoint_id == ep.id, Incident.ended_at.is_(None)).order_by(Incident.id.desc()))
            if not is_up:
                if ep.consecutive_failures == 0:
                    ep.failure_started_at = checked_at
                ep.consecutive_failures += 1
                ep.consecutive_successes = 0
                if incident:
                    incident.failure_count += 1
                    incident.last_error_type, incident.last_error_message, incident.last_status_code = error_type, error_message, status_code
                elif ep.consecutive_failures >= ep.failure_threshold:
                    first_check = db.scalar(select(Check).where(Check.endpoint_id == ep.id, Check.is_up.is_(False),
                                              Check.checked_at >= ep.failure_started_at).order_by(Check.checked_at, Check.id).limit(1))
                    first_check = first_check or check
                    incident = Incident(endpoint_id=ep.id, endpoint_name=ep.name, endpoint_url=ep.url,
                                        method=ep.method, expected_status=ep.expected_status,
                                        started_at=ep.failure_started_at, detected_at=checked_at,
                                        first_error_type=first_check.error_type, first_error_message=first_check.error_message,
                                        first_status_code=first_check.status_code, last_error_type=error_type,
                                        last_error_message=error_message, last_status_code=status_code,
                                        failure_count=ep.consecutive_failures, notes="", is_demo=False)
                    db.add(incident)
                    db.flush()
                    notify = ("incident.opened", incident_dict(incident, checked_at))
                    logger.warning("incident_opened endpoint_id=%s incident_id=%s failures=%s type=%s status=%s",
                                   ep.id, incident.id, ep.consecutive_failures, error_type, status_code)
                logger.warning("check_failed endpoint_id=%s error_type=%s status=%s response_ms=%s", ep.id, error_type, status_code, response_ms)
            else:
                ep.consecutive_successes += 1
                ep.consecutive_failures = 0
                ep.failure_started_at = None
                if incident and ep.consecutive_successes >= ep.recovery_threshold:
                    incident.ended_at, incident.end_reason = checked_at, "recovered"
                    db.flush()
                    notify = ("incident.resolved", incident_dict(incident, checked_at))
                    logger.info("incident_resolved endpoint_id=%s incident_id=%s", ep.id, incident.id)
                logger.info("check_ok endpoint_id=%s status=%s response_ms=%s", ep.id, status_code, response_ms)
            db.commit()
            result = {"id": check.id, "endpoint_id": ep.id, "checked_at": iso(check.checked_at),
                      "is_up": check.is_up, "status_code": check.status_code, "response_ms": check.response_ms,
                      "error_type": check.error_type, "error_message": check.error_message}
        if notify:
            await send_webhook(app, *notify)
        return result


async def scheduler_loop(app) -> None:
    runtime = _runtime(app)
    semaphore = asyncio.Semaphore(app.state.settings.check_concurrency)

    async def run(endpoint_id: int):
        try:
            async with semaphore:
                await perform_check(app, endpoint_id, only_if_due=True)
        except CheckUnavailable:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduler_check_failed endpoint_id=%s", endpoint_id)
        finally:
            runtime["running"].discard(endpoint_id)

    while True:
        try:
            with app.state.session_factory() as db:
                due = list(db.scalars(select(Endpoint.id).where(Endpoint.enabled.is_(True), Endpoint.archived.is_(False),
                           Endpoint.is_demo.is_(False), (Endpoint.next_check_at.is_(None)) | (Endpoint.next_check_at <= utcnow()))))
            for endpoint_id in due:
                if endpoint_id not in runtime["running"]:
                    runtime["running"].add(endpoint_id)
                    task = asyncio.create_task(run(endpoint_id), name=f"opis-check-{endpoint_id}")
                    runtime["tasks"].add(task)
                    task.add_done_callback(runtime["tasks"].discard)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduler_iteration_failed")
        await asyncio.sleep(app.state.settings.scheduler_interval)
