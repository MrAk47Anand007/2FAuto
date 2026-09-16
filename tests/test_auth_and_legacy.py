import pytest


def test_invalid_login_stays_on_login_page(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.text


def test_legacy_single_secret_otp_still_works(client):
    response = client.get("/otp", headers={"X-API-Key": "test-api-key"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["otp"]) == 6
    assert payload["period"] == 30
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_legacy_global_key_path_is_explicitly_disabled(client):
    from app.core import config

    config.settings.LEGACY_API_ENABLED = False
    response = client.get("/otp", headers={"X-API-Key": "test-api-key"})
    assert response.status_code == 410


def test_production_settings_reject_sample_and_insecure_values(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "your-strong-random-api-key")
    monkeypatch.setenv("SESSION_SECRET", "change-this-session-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", "change-this-admin-password")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("ENABLE_DOCS", "true")

    with pytest.raises(SystemExit):
        Settings()


def test_login_cookie_uses_secure_flag_when_configured(client):
    from app.core import config
    from tests.conftest import login

    config.settings.COOKIE_SECURE = True
    response = login(client)

    assert response.status_code in (302, 303)
    assert "Secure" in response.headers["set-cookie"]


def test_logout_requires_csrf_and_revokes_session(client):
    from tests.conftest import csrf_token, login

    login_response = login(client)
    assert login_response.status_code in (302, 303)
    assert client.get("/dashboard").status_code == 200

    missing_csrf = client.post("/logout", follow_redirects=False)
    assert missing_csrf.status_code == 403

    logout_response = client.post(
        "/logout",
        data={"csrf_token": csrf_token(client, "/dashboard")},
        follow_redirects=False,
    )
    assert logout_response.status_code in (302, 303)
    assert client.get("/dashboard").status_code == 401


def test_admin_step_up_form_authorizes_sensitive_actions(client):
    from tests.conftest import csrf_token, login

    login(client)
    response = client.post(
        "/admin/step-up",
        data={"password": "admin-pass", "csrf_token": csrf_token(client)},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def test_session_list_and_owned_session_revocation(client):
    from tests.conftest import csrf_token, login

    login(client)
    sessions = client.get("/api/v1/me/sessions")
    assert sessions.status_code == 200
    current = next(item for item in sessions.json()["sessions"] if item["current"])

    revoked = client.delete(
        f"/api/v1/me/sessions/{current['id']}",
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert revoked.status_code == 200
    assert client.get("/dashboard").status_code == 401


def test_login_throttle_blocks_repeated_failures(client):
    from tests.conftest import login

    for _ in range(5):
        response = login(client, password="wrong-password")
        assert response.status_code == 401

    blocked = login(client)
    assert blocked.status_code == 401


def test_disabled_username_is_not_recreated_by_bootstrap_lookup(client):
    from app.core.database import (
        create_user,
        disable_user,
        get_user_by_username,
        list_users,
    )
    from app.core.security import hash_password
    from app.main import bootstrap_admin_user
    from app.core import config

    create_user("replacement-admin", hash_password("replacement-pass"), "admin")
    assert disable_user("replacement-admin") is True

    config.settings.ADMIN_USERNAME = "replacement-admin"
    config.settings.ADMIN_PASSWORD = "replacement-pass"
    bootstrap_admin_user()

    assert get_user_by_username("replacement-admin") is None
    inactive = get_user_by_username("replacement-admin", include_inactive=True)
    assert inactive is not None
    assert inactive["is_active"] == 0
    assert sum(user["username"] == "replacement-admin" for user in list_users()) == 1


def test_final_active_admin_cannot_be_disabled(client):
    from app.core.database import create_user, disable_user, get_user_by_username
    from app.core.security import hash_password

    create_user("second-admin", hash_password("second-admin-pass"), "admin")
    assert disable_user("admin") is True
    assert disable_user("second-admin") is False
    assert get_user_by_username("second-admin", include_inactive=True)["is_active"] == 1
