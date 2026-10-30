import os
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.database import Base, make_engine
from app.main import create_app


@pytest.fixture
def app_client(tmp_path):
    # OPIS_TEST_DATABASE_URL must point to a dedicated, disposable database.
    url = os.getenv("OPIS_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    engine = make_engine(url)
    Base.metadata.drop_all(engine)
    app = create_app(Settings(database_url=url, demo_data=False, scheduler_enabled=False,
                              allow_private_targets=True, scheduler_interval=0.25), engine)
    with TestClient(app) as client:
        yield app, client
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def add_endpoint(app_client):
    app, client = app_client
    def add(**overrides):
        payload = {"name": "Payment API", "url": "https://monitor.example/health",
                   "failure_threshold": 2, "recovery_threshold": 1}
        payload.update(overrides)
        response = client.post("/api/endpoints", json=payload)
        assert response.status_code == 201, response.text
        return response.json()
    return add
