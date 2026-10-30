"""Optional browser smoke test: pip install -r requirements-ui.txt; playwright install chromium."""
import json
from urllib.parse import urlsplit
import httpx
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from app.config import Settings
from app.database import make_engine
from app.main import create_app


def test_add_failure_incident_notes_and_recovery_in_browser(tmp_path):
    url = f"sqlite:///{tmp_path / 'browser.db'}"
    app = create_app(Settings(database_url=url, demo_data=False, scheduler_enabled=False,
                              allow_private_targets=True), make_engine(url))
    results = iter([503, 200])
    notifications = []

    def transport(request):
        if request.url.host == 'hooks.example':
            notifications.append(json.loads(request.content))
            return httpx.Response(204, request=request)
        return httpx.Response(next(results), request=request)

    app.state.http_transport = httpx.MockTransport(transport)
    with TestClient(app) as api, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1280, 'height':900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        # All browser requests are routed through the isolated TestClient; no live server or internet is needed.
        def route_request(route):
            request = route.request
            parsed = urlsplit(request.url)
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            response = api.request(request.method, path, content=request.post_data_buffer,
                                   headers={'Content-Type': request.headers.get('content-type', '')})
            headers = {k:v for k,v in response.headers.items() if k.lower() not in
                       {'content-encoding', 'transfer-encoding', 'connection', 'content-length'}}
            route.fulfill(status=response.status_code, headers=headers, body=response.content)

        page.route('**/*', route_request)
        page.goto('http://opis.test/', wait_until='networkidle')
        page.locator('.nav-item[data-page="alerts"]').click()
        page.wait_for_selector('#webhookForm')
        page.fill('#webhookUrl', 'https://hooks.example/events')
        page.locator('#webhookForm button[type=submit]').click()
        page.wait_for_selector('text=Webhook berhasil disimpan')
        page.locator('.top-add').click()
        page.fill('#f-name', 'Layanan Tes')
        page.fill('#f-url', 'https://probe.example/health')
        page.fill('#f-failure_threshold', '1')
        page.locator('#endpointForm button[type=submit]').click()
        page.wait_for_selector('text=Scheduler nonaktif')
        page.locator('.nav-item[data-page="endpoints"]').click()
        page.wait_for_selector('text=Layanan Tes')
        assert 'Menunggu' in page.locator('#endpointRows').inner_text()
        page.locator('#endpointRows [data-action="check-endpoint"]').click()
        page.wait_for_selector('text=Pemeriksaan gagal:')
        assert api.get('/api/incidents').json()[0]['status'] == 'open'
        page.locator('.nav-item[data-page="incidents"]').click()
        page.wait_for_selector('h1:has-text("Riwayat insiden")')
        page.locator('.full-table [data-action="incident-detail"]').first.click()
        page.wait_for_selector('#notesForm')
        page.fill('#notesForm textarea', 'Periksa upstream.')
        page.locator('#notesForm button[type=submit]').click()
        page.wait_for_selector('text=Catatan investigasi disimpan')
        page.locator('.drawer [data-action="close-modal"]').click()
        page.locator('.nav-item[data-page="endpoints"]').click()
        page.wait_for_selector('#endpointRows')
        page.locator('#endpointRows [data-action="check-endpoint"]').click()
        page.wait_for_selector('text=Pemeriksaan berhasil.')
        incident = api.get('/api/incidents').json()[0]
        assert incident['status'] == 'resolved' and incident['notes'] == 'Periksa upstream.'
        assert [item['event'] for item in notifications] == ['incident.opened', 'incident.resolved']
        assert errors == []
        browser.close()
