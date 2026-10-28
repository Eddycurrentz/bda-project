from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import security_store
import webapp


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(security_store, "DB_PATH", tmp_path / "sentinel-test.sqlite3")
    webapp._records.clear()
    webapp._alerts.clear()
    webapp._alert_statuses.clear()
    webapp._demo_touched = False
    webapp._demo_active = False
    webapp._login_attempts.clear()
    webapp._request_attempts.clear()
    with TestClient(webapp.app) as test_client:
        csrf = test_client.get("/auth/csrf").json()["csrf_token"]
        test_client.headers.update({"X-CSRF-Token": csrf})
        yield test_client


def login(client, email="admin@sentinelpulse.local", password="SentinelDemo!2026", **extra):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return client.post("/auth/login", json={"email": email, "password": password, **extra},
                       headers={"X-CSRF-Token": csrf})
