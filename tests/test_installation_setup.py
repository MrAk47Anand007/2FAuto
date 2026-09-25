from fastapi.testclient import TestClient
import pytest


def with_peer_address(app, address):
    async def wrapped(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": (address, 49152)}
        await app(scope, receive, send)

    return wrapped


def test_packaged_setup_is_local_single_use_and_unlocks_api(client, monkeypatch, tmp_path):
    from app.core.config import settings
    from app.main import create_app

    data_dir = tmp_path / "vault"
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html>setup shell</html>", encoding="utf-8")
    monkeypatch.setattr(settings, "APP_ENV", "packaged")
    monkeypatch.setattr(settings, "DATABASE_PATH", str(data_dir / "otp.db"))
    monkeypatch.setattr(settings, "PACKAGED_DATA_DIR", str(data_dir), raising=False)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(settings, "SECRET_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "SESSION_SECRET", "")
    monkeypatch.setattr(settings, "LEGACY_API_ENABLED", False)

    with TestClient(with_peer_address(create_app(packaged_ui_dir=ui_dir), "127.0.0.1"),
                    base_url="http://127.0.0.1:8000") as app:
        assert app.get("/ready").status_code == 503
        assert app.get("/api/v1/me").status_code == 503
        assert app.get("/admin/api/v1/admin/users").status_code == 503
        assert app.get("/api/ui/portals").status_code == 503
        assert app.get("/", follow_redirects=False).headers["location"] == "/setup"
        assert app.get("/setup").status_code == 200
        assert app.get("/api/setup/status").json()["configured"] is False
        token = app.get("/api/setup/status").json()["setup_token"]

        body = {"username": "owner", "password": "correct horse battery staple"}
        assert app.post("/api/setup/initialize", json=body).status_code == 403
        assert app.post(
            "/api/setup/initialize", json={**body, "password": "short"},
            headers={"x-setup-token": token},
        ).status_code == 422
        assert app.post(
            "/api/setup/initialize", json={**body, "password": "change-this-admin-password"},
            headers={"x-setup-token": token},
        ).status_code == 422
        from app.core import installation

        real_hash_password = installation.hash_password
        def interrupted_hash(_password):
            raise RuntimeError("simulated interruption after key creation")
        monkeypatch.setattr(installation, "hash_password", interrupted_hash)
        with pytest.raises(RuntimeError, match="simulated interruption"):
            installation.initialize_administrator(body["username"], body["password"])
        monkeypatch.setattr(installation, "hash_password", real_hash_password)
        assert app.get("/ready").status_code == 503
        assert (data_dir / "vault-keys.bin").exists()
        initialized = app.post(
            "/api/setup/initialize", json=body, headers={"x-setup-token": token}
        )
        assert initialized.status_code == 201, initialized.text
        assert app.get("/ready").status_code == 200
        assert app.get("/api/setup/status").json() == {"configured": True}
        assert app.post(
            "/api/setup/initialize", json=body, headers={"x-setup-token": token}
        ).status_code == 409
        assert app.post(
            "/api/v1/auth/login", json={"username": "owner", "password": body["password"]}
        ).status_code == 200

    assert (data_dir / "otp.db").exists()
    assert (data_dir / "vault-keys.bin").exists()
    assert body["password"].encode() not in (data_dir / "vault-keys.bin").read_bytes()
    assert b"SECRET_ENCRYPTION_KEY" not in (data_dir / "vault-keys.bin").read_bytes()

    monkeypatch.setattr(settings, "SECRET_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "SESSION_SECRET", "")
    with TestClient(with_peer_address(create_app(packaged_ui_dir=ui_dir), "127.0.0.1"),
                    base_url="http://127.0.0.1:8000") as restarted:
        assert restarted.get("/ready").status_code == 200
        assert restarted.post(
            "/api/v1/auth/login", json={"username": "owner", "password": body["password"]}
        ).status_code == 200

    (data_dir / "vault-keys.bin").unlink()
    with TestClient(with_peer_address(create_app(packaged_ui_dir=ui_dir), "127.0.0.1"),
                    base_url="http://127.0.0.1:8000") as missing_key:
        assert missing_key.get("/ready").status_code == 503
        token = missing_key.get("/api/setup/status").json()["setup_token"]
        assert missing_key.post(
            "/api/setup/initialize", json=body, headers={"x-setup-token": token}
        ).status_code == 409


def test_unconfigured_setup_rejects_non_loopback_clients(client, monkeypatch, tmp_path):
    from app.core.config import settings
    from app.main import create_app

    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html>setup shell</html>", encoding="utf-8")
    monkeypatch.setattr(settings, "APP_ENV", "packaged")
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "vault" / "otp.db"))
    monkeypatch.setattr(settings, "PACKAGED_DATA_DIR", str(tmp_path / "vault"), raising=False)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(settings, "SECRET_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "SESSION_SECRET", "")

    with TestClient(with_peer_address(create_app(packaged_ui_dir=ui_dir), "192.0.2.10"),
                    base_url="http://192.0.2.10:8000") as remote:
        assert remote.get("/api/setup/status").status_code == 403
        assert remote.get("/login").status_code == 403


def test_packaged_database_defaults_to_application_data(client, monkeypatch, tmp_path):
    from app.core.config import Settings

    monkeypatch.setenv("APP_ENV", "packaged")
    monkeypatch.setenv("TWOFAUTO_PACKAGED_DATA_DIR", str(tmp_path / "vault"))
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    settings = Settings()
    assert settings.DATABASE_PATH == str(tmp_path / "vault" / "otp_service.db")
