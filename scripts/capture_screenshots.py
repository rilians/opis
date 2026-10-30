"""Capture actual Opis screens using an isolated, synthetic dataset.

Run from the project root after installing requirements-ui.txt and Chromium:
    python scripts/capture_screenshots.py
No live Opis database or real network endpoints are modified.
"""
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from app.config import Settings
from app.database import make_engine
from app.main import create_app

OUTPUT = ROOT / "docs" / "screenshots"
OUTPUT.mkdir(parents=True, exist_ok=True)


def capture():
    with tempfile.TemporaryDirectory(prefix="opis-screenshots-") as folder:
        database_url = f"sqlite:///{Path(folder) / 'demo.db'}"
        app = create_app(Settings(database_url=database_url, demo_data=True, scheduler_enabled=True),
                         make_engine(database_url))
        with TestClient(app) as client, sync_playwright() as playwright:
            incidents = client.get("/api/incidents?status=open").json()
            if incidents:
                client.patch(f"/api/incidents/{incidents[0]['id']}", json={
                    "notes": "Contoh investigasi: periksa log gateway dan layanan upstream pada saat HTTP 503. Penyebab belum terkonfirmasi."
                })
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 1440, "height": 1080},
                                          locale="id-ID", timezone_id="Asia/Jakarta", device_scale_factor=1)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            # The browser is entirely backed by an isolated TestClient. No actual HTTP
            # endpoint is contacted and no state in the user's running app is changed.
            def route_request(route):
                request = route.request
                parsed = urlsplit(request.url)
                if parsed.netloc != "opis.test":
                    route.abort()
                    return
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                response = client.request(request.method, path, content=request.post_data_buffer,
                                          headers={"Content-Type": request.headers.get("content-type", "")})
                headers = {k: v for k, v in response.headers.items() if k.lower() not in
                           {"content-encoding", "transfer-encoding", "connection", "content-length"}}
                route.fulfill(status=response.status_code, headers=headers, body=response.content)

            page.route("**/*", route_request)

            def save(name, full_page=True):
                page.evaluate("document.fonts.ready")
                page.wait_for_timeout(220)  # let UI opening transitions finish
                page.screenshot(path=str(OUTPUT / name), full_page=full_page, animations="disabled")
                print(f"Captured {name}")

            page.goto("http://opis.test/", wait_until="networkidle")
            page.wait_for_selector(".metric-card")
            save("01-overview.png")

            page.locator('.nav-item[data-page="endpoints"]').click()
            page.wait_for_selector("#endpointRows")
            save("02-endpoints.png")

            page.locator(".top-add").click()
            page.wait_for_selector("#endpointForm")
            save("03-add-endpoint.png", full_page=False)
            page.locator('#endpointForm [data-action="close-modal"]').click()

            page.locator('#endpointRows [data-action="endpoint-detail"]').filter(has_text="Payment Service").click()
            page.wait_for_selector(".drawer .evidence-list")
            save("04-endpoint-detail.png", full_page=False)
            page.locator('.drawer [data-action="close-modal"]').click()

            page.locator('.nav-item[data-page="incidents"]').click()
            page.wait_for_selector('h1:has-text("Riwayat insiden")')
            save("05-incidents.png")

            page.locator('.full-table [data-action="incident-detail"]').first.click()
            page.wait_for_selector("#notesForm")
            save("06-incident-detail.png", full_page=False)
            page.locator('.drawer [data-action="close-modal"]').click()

            page.locator('.nav-item[data-page="sla"]').click()
            page.wait_for_selector('h1:has-text("Laporan SLA")')
            page.wait_for_selector('.full-table tbody tr')
            save("07-sla-report.png")

            page.locator('.nav-item[data-page="alerts"]').click()
            page.wait_for_selector("#webhookForm")
            save("08-notifications.png")

            page.locator('.nav-item[data-page="settings"]').click()
            page.wait_for_selector("#settingsForm")
            save("09-settings.png")

            page.set_viewport_size({"width": 390, "height": 844})
            page.goto("http://opis.test/#overview", wait_until="networkidle")
            page.wait_for_selector(".metric-card")
            save("10-mobile-overview.png", full_page=False)

            if errors:
                raise RuntimeError("Browser errors while capturing screenshots: " + "; ".join(errors))
            context.close()
            browser.close()


if __name__ == "__main__":
    capture()
