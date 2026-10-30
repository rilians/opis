import asyncio
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.database import make_engine, utcnow
from app.main import create_app
from app.models import Endpoint
from app import monitor


@pytest.mark.asyncio
async def test_scheduler_only_runs_enabled_real_due_endpoints(app_client, monkeypatch):
    app, client = app_client
    ep = client.post('/api/endpoints', json={'name':'real', 'url':'https://real.example'}).json()
    with app.state.session_factory() as db:
        db.add(Endpoint(name='paused', url='https://paused.example', enabled=False, archived=False, is_demo=False, next_check_at=utcnow()))
        db.add(Endpoint(name='demo', url='https://demo.example', enabled=True, archived=False, is_demo=True, next_check_at=utcnow()))
        db.add(Endpoint(name='not due', url='https://future.example', enabled=True, archived=False, is_demo=False, next_check_at=utcnow()+timedelta(hours=1)))
        db.commit()
    called = []
    seen = asyncio.Event()
    async def fake_check(application, endpoint_id, only_if_due=False):
        called.append((endpoint_id, only_if_due))
        seen.set()
    monkeypatch.setattr(monitor, 'perform_check', fake_check)
    task = asyncio.create_task(monitor.scheduler_loop(app))
    await asyncio.wait_for(seen.wait(), timeout=2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.gather(*list(app.state.runtime['tasks']), return_exceptions=True)
    assert called == [(ep['id'], True)]


@pytest.mark.asyncio
async def test_dns_private_resolution_is_blocked(monkeypatch):
    loop = asyncio.get_running_loop()
    async def fake_dns(*args, **kwargs):
        return [(2, 1, 6, '', ('10.0.0.9', 443))]
    monkeypatch.setattr(loop, 'getaddrinfo', fake_dns)
    with pytest.raises(monitor.TargetBlocked):
        await monitor.validate_target('https://monitor.example/health', False)


def test_demo_is_explicit_simulation_and_not_reseeded_after_deletion(tmp_path):
    url = f"sqlite:///{tmp_path / 'demo.db'}"
    engine = make_engine(url)
    app = create_app(Settings(database_url=url, demo_data=True, scheduler_enabled=False), engine)
    with TestClient(app) as client:
        data = client.get('/api/dashboard').json()
        assert data['demo_count'] == 5 and data['total_endpoints'] == 5
        assert data['active_incidents'] == 1
        endpoint = data['endpoints'][0]
        assert endpoint['is_demo'] is True
        result = client.post(f"/api/endpoints/{endpoint['id']}/check")
        assert result.status_code == 409 and 'simulasi' in result.json()['detail']
        assert client.delete('/api/demo').json()['removed_endpoints'] == 5
        assert client.get('/api/dashboard').json()['total_endpoints'] == 0
    with TestClient(app) as client:
        assert client.get('/api/dashboard').json()['total_endpoints'] == 0
        assert client.get('/api/settings').json()['demo_count_all'] == 0
