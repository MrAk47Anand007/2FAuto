import pyotp
from pathlib import Path


def test_admin_can_create_portal_and_dashboard_lists_otp_without_secret(client):
    from tests.conftest import csrf_token, login, step_up

    login_response = login(client)
    assert login_response.status_code in (302, 303)
    assert step_up(client).status_code == 200

    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    assert "Manage OTP Access" in admin_page.text

    secret = pyotp.random_base32()
    create_response = client.post(
        "/admin/portals",
        data={
            "portal_name": "vendor-login",
            "display_name": "Vendor Login",
            "secret": secret,
            "period": "30",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert create_response.status_code in (302, 303)

    grant_response = client.post(
        "/admin/portals/vendor-login/grants",
        data={
            "username": "admin",
            "expires_in_days": "0",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert grant_response.status_code in (302, 303)

    dashboard_response = client.get("/api/ui/portals")
    assert dashboard_response.status_code == 200
    payload = dashboard_response.json()
    assert payload["portals"][0]["portal_name"] == "vendor-login"
    assert payload["portals"][0]["display_name"] == "Vendor Login"
    assert "secret" not in payload["portals"][0]
    assert "otp" not in payload["portals"][0]
    assert payload["portals"][0]["period"] == 30

    reveal_response = client.post(
        "/api/ui/portals/vendor-login/otp",
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert reveal_response.status_code == 200
    assert len(reveal_response.json()["otp"]) == 6


def test_portal_otp_endpoint_requires_api_key_and_returns_named_otp(client):
    from tests.conftest import csrf_token, login, step_up

    login(client)
    assert step_up(client).status_code == 200
    secret = pyotp.random_base32()
    client.post(
        "/admin/portals",
        data={
            "portal_name": "bank",
            "display_name": "Bank",
            "secret": secret,
            "period": "30",
            "csrf_token": csrf_token(client),
        },
    )

    unauthorized = client.get("/otp/bank")
    assert unauthorized.status_code == 401

    authorized = client.get("/otp/bank", headers={"X-API-Key": "test-api-key"})
    assert authorized.status_code == 200
    assert authorized.json()["portal_name"] == "bank"
    assert len(authorized.json()["otp"]) == 6


def test_business_user_can_login_and_view_dashboard(client):
    from tests.conftest import csrf_token, login, step_up

    login(client)
    assert step_up(client).status_code == 200
    create_user = client.post(
        "/admin/users",
        data={
            "username": "business",
            "password": "business-pass",
            "role": "user",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert create_user.status_code in (302, 303)

    client.post(
        "/logout",
        data={"csrf_token": csrf_token(client, "/dashboard")},
        follow_redirects=False,
    )
    user_login = login(client, username="business", password="business-pass")
    assert user_login.status_code in (302, 303)

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Live OTP Dashboard" in dashboard.text


def test_dashboard_bulk_endpoint_is_retired_and_readiness_is_available(client):
    from tests.conftest import login

    login(client)
    assert client.get("/ready").status_code == 200
    retired = client.get("/api/ui/otps")
    assert retired.status_code == 410


def test_portal_secret_is_encrypted_before_database_write(client):
    from app.core import config
    from app.core.database import ENCRYPTED_SECRET_PLACEHOLDER, get_db
    from tests.conftest import csrf_token, login, step_up

    login(client)
    assert step_up(client).status_code == 200
    secret = pyotp.random_base32()
    response = client.post(
        "/admin/portals",
        data={
            "portal_name": "encrypted-portal",
            "display_name": "Encrypted Portal",
            "secret": secret,
            "period": "30",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    with get_db() as db:
        row = db.execute(
            """
            SELECT secret, secret_ciphertext, secret_nonce,
                   encryption_version, key_version
            FROM otp_entries
            WHERE portal_name = ?
            """,
            ("encrypted-portal",),
        ).fetchone()

    assert row["secret"] == ENCRYPTED_SECRET_PLACEHOLDER
    assert row["secret_ciphertext"]
    assert row["secret_nonce"]
    assert row["encryption_version"] == 1
    assert row["key_version"] == "v1"
    assert secret.encode() not in Path(config.settings.DATABASE_PATH).read_bytes()


def test_admin_accepts_local_totp_provisioning_uri(client):
    from tests.conftest import csrf_token, login, step_up

    login(client)
    assert step_up(client).status_code == 200
    secret = pyotp.random_base32()
    uri = (
        "otpauth://totp/Example:Browser?secret="
        f"{secret}&issuer=Example&algorithm=SHA1&digits=6&period=60"
    )
    response = client.post(
        "/admin/portals",
        data={
            "portal_name": "uri-portal",
            "display_name": "URI Portal",
            "secret": uri,
            "period": "30",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    grant = client.post(
        "/admin/portals/uri-portal/grants",
        data={
            "username": "admin",
            "expires_in_days": "0",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert grant.status_code in (302, 303)

    metadata = client.get("/api/ui/portals")
    assert metadata.status_code == 200
    assert metadata.json()["portals"][0]["period"] == 60


def test_legacy_plaintext_row_is_migrated_and_remains_readable(client):
    from app.core.database import get_db, init_database
    from tests.conftest import login

    login(client)
    secret = pyotp.random_base32()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO otp_entries
                (portal_name, display_name, secret, period, is_active,
                 created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, 1, 1)
            """,
            ("legacy-portal", "Legacy Portal", secret, 30, 1),
        )

    init_database()

    with get_db() as db:
        row = db.execute(
            """
            SELECT secret, secret_ciphertext, secret_nonce
            FROM otp_entries
            WHERE portal_name = ?
            """,
            ("legacy-portal",),
        ).fetchone()

    assert row["secret"] == "[encrypted]"
    assert row["secret_ciphertext"]
    assert row["secret_nonce"]

    response = client.get(
        "/otp/legacy-portal",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    assert len(response.json()["otp"]) == 6
