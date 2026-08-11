import os
import tempfile

import pyotp
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db_path)

    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("OTP_SECRET", pyotp.random_base32())
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass")

    from app.core import config

    config.settings.API_KEY = "test-api-key"
    config.settings.OTP_SECRET = pyotp.random_base32()
    config.settings.DATABASE_PATH = db_path
    config.settings.SESSION_SECRET = "test-session-secret"
    config.settings.ADMIN_USERNAME = "admin"
    config.settings.ADMIN_PASSWORD = "admin-pass"
    config.settings.ENABLE_DOCS = False

    from app.core.database import init_database
    from app.main import create_app

    init_database()
    app = create_app()

    with TestClient(app) as test_client:
        yield test_client

    if os.path.exists(db_path):
        os.unlink(db_path)


def login(client, username="admin", password="admin-pass"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
