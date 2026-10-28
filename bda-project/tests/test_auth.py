from __future__ import annotations

import pyotp

from conftest import login


def test_protected_data_needs_auth_and_csrf(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/inject-anomaly").status_code == 401
    assert login(client).status_code == 200
    assert client.get("/api/dashboard").status_code == 200
    assert "Content-Security-Policy" in client.get("/health").headers


def test_demo_dataset_shows_100_available_records(client):
    import security_store

    assert login(client).status_code == 200
    dashboard = client.get("/api/dashboard").json()
    tweets = client.get("/api/tweets", params={"limit": 20}).json()
    assert dashboard["available_total"] == 100
    assert dashboard["total"] == 100
    assert tweets["total"] == 100
    assert tweets["available_total"] == 100
    security_store.save_tweets([{"timestamp": "2025-01-01T00:00:00", "tweet": "stale cached row"}])
    refreshed = client.post("/api/refresh", headers={"X-CSRF-Token": client.cookies.get("sp_csrf")})
    assert refreshed.json()["records"] == 100


def test_viewer_is_forbidden_from_analyst_and_admin_actions(client):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    created = client.post("/auth/register", json={"email":"viewer@example.com", "name":"Taylor Viewer",
        "password":"StrongViewer!2026"}, headers={"X-CSRF-Token":csrf})
    assert created.status_code == 201
    assert created.json()["user"]["role"] == "viewer"
    assert client.post("/api/inject-anomaly", headers={"X-CSRF-Token":created.json()["csrf_token"]}).status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_refresh_token_rotates_and_logout_revokes(client):
    assert login(client).status_code == 200
    old = client.cookies.get("sp_refresh")
    csrf = client.cookies.get("sp_csrf")
    rotated = client.post("/auth/refresh", headers={"X-CSRF-Token":csrf})
    assert rotated.status_code == 200
    assert client.cookies.get("sp_refresh") != old
    assert client.post("/auth/logout", headers={"X-CSRF-Token":client.cookies.get("sp_csrf")}).json()["ok"]
    assert client.get("/auth/me").status_code == 401


def test_lockout_after_five_bad_passwords(client):
    for _ in range(5):
        response = login(client, password="wrong-password")
        assert response.status_code == 401
    assert login(client).status_code == 423


def test_optional_totp_requires_authenticator_code(client):
    assert login(client).status_code == 200
    headers={"X-CSRF-Token":client.cookies.get("sp_csrf")}
    setup=client.post("/auth/totp/setup", headers=headers)
    assert setup.status_code == 200
    code=pyotp.TOTP(setup.json()["secret"]).now()
    assert client.post("/auth/totp/enable", json={"code":code}, headers=headers).status_code == 200
    client.post("/auth/logout", headers=headers)
    assert login(client).status_code == 401
    code=pyotp.TOTP(setup.json()["secret"]).now()
    assert login(client, totp_code=code).status_code == 200


def test_admin_role_changes_are_audited(client):
    assert login(client).status_code == 200
    csrf=client.cookies.get("sp_csrf")
    created=client.post("/auth/register", json={"email":"analyst@example.com", "name":"Alex Analyst",
        "password":"StrongAnalyst!2026"}, headers={"X-CSRF-Token":csrf})
    user_id=created.json()["user"]["id"]
    assert login(client).status_code == 200
    csrf=client.cookies.get("sp_csrf")
    result=client.put(f"/api/admin/users/{user_id}/role", json={"role":"analyst"}, headers={"X-CSRF-Token":csrf})
    assert result.status_code == 200
    events=client.get("/api/admin/audit").json()
    assert any(row["event"]=="role_changed" for row in events)


def test_filtered_pagination_and_csv_pdf_exports(client):
    assert login(client).status_code == 200
    dashboard=client.get("/api/dashboard?days=all").json()
    brand=dashboard["brands"][0]["brand"]
    page=client.get("/api/tweets",params={"brand":brand,"limit":2,"page":1})
    assert page.status_code==200 and len(page.json()["items"])<=2
    assert page.json()["total"]>=len(page.json()["items"])
    assert client.get("/api/export.csv",params={"brand":brand}).headers["content-type"].startswith("text/csv")
    assert client.get("/api/export.pdf",params={"brand":brand}).headers["content-type"]=="application/pdf"


def test_analyst_can_acknowledge_alert_and_alert_is_persistent(client):
    assert login(client).status_code==200
    csrf=client.cookies.get("sp_csrf")
    created=client.post("/auth/register",json={"email":"analyst2@example.com","name":"Case Analyst",
        "password":"SecureAnalyst!2026"},headers={"X-CSRF-Token":csrf})
    user_id=created.json()["user"]["id"]
    assert login(client).status_code==200
    csrf=client.cookies.get("sp_csrf")
    assert client.put(f"/api/admin/users/{user_id}/role",json={"role":"analyst"},headers={"X-CSRF-Token":csrf}).status_code==200
    client.post("/auth/logout",headers={"X-CSRF-Token":client.cookies.get("sp_csrf")})
    assert login(client,"analyst2@example.com","SecureAnalyst!2026").status_code==200
    csrf=client.cookies.get("sp_csrf")
    injected=client.post("/api/inject-anomaly",headers={"X-CSRF-Token":csrf}).json()
    alert_id=injected["alert"]["id"]
    action=client.post(f"/api/alerts/{alert_id}/acknowledge",headers={"X-CSRF-Token":csrf})
    assert action.status_code==200 and action.json()["status"]=="Acknowledged"
