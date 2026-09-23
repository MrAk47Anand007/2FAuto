def test_spa_login_bootstrap_and_logout(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-pass"},
    )
    assert response.status_code == 200
    login = response.json()
    assert login["username"] == "admin"
    assert login["role"] == "admin"
    assert login["csrf_token"]
    assert "otp_session=" in response.headers["set-cookie"]

    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["csrf_token"] == login["csrf_token"]
    assert me.json()["session_expires_at"]

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": login["csrf_token"]},
    )
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}
    assert client.get("/api/v1/me").status_code == 401


def test_spa_bootstrap_does_not_touch_idle_session(client, monkeypatch):
    from app.core import database, security

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-pass"},
    ).json()
    # Read the database as the stable source of last-active evidence for the
    # browser cookie session.
    with database.get_db() as db:
        before = db.execute("SELECT last_active_at FROM sessions ORDER BY id DESC LIMIT 1").fetchone()["last_active_at"]
    monkeypatch.setattr(security.time, "time", lambda: before + 120)
    assert client.get("/api/v1/me").status_code == 200
    with database.get_db() as db:
        after = db.execute("SELECT last_active_at FROM sessions ORDER BY id DESC LIMIT 1").fetchone()["last_active_at"]
    assert after == before
    assert login["csrf_token"]


def test_spa_admin_metadata_endpoints(client):
    from tests.conftest import login

    login(client)
    for path, key in (
        ("/admin/api/v1/admin/portals", "portals"),
        ("/admin/api/v1/admin/users", "users"),
        ("/admin/api/v1/admin/teams", "teams"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert key in response.json()
