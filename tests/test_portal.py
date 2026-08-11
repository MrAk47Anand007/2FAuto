import pyotp


def test_admin_can_create_portal_and_dashboard_lists_otp_without_secret(client):
    from tests.conftest import login

    login_response = login(client)
    assert login_response.status_code in (302, 303)

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
        },
        follow_redirects=False,
    )
    assert create_response.status_code in (302, 303)

    dashboard_response = client.get("/api/ui/otps")
    assert dashboard_response.status_code == 200
    payload = dashboard_response.json()
    assert payload["otps"][0]["portal_name"] == "vendor-login"
    assert payload["otps"][0]["display_name"] == "Vendor Login"
    assert "secret" not in payload["otps"][0]
    assert len(payload["otps"][0]["otp"]) == 6
    assert payload["otps"][0]["period"] == 30


def test_portal_otp_endpoint_requires_api_key_and_returns_named_otp(client):
    from tests.conftest import login

    login(client)
    secret = pyotp.random_base32()
    client.post(
        "/admin/portals",
        data={
            "portal_name": "bank",
            "display_name": "Bank",
            "secret": secret,
            "period": "30",
        },
    )

    unauthorized = client.get("/otp/bank")
    assert unauthorized.status_code == 401

    authorized = client.get("/otp/bank", headers={"X-API-Key": "test-api-key"})
    assert authorized.status_code == 200
    assert authorized.json()["portal_name"] == "bank"
    assert len(authorized.json()["otp"]) == 6


def test_business_user_can_login_and_view_dashboard(client):
    from tests.conftest import login

    login(client)
    create_user = client.post(
        "/admin/users",
        data={"username": "business", "password": "business-pass", "role": "user"},
        follow_redirects=False,
    )
    assert create_user.status_code in (302, 303)

    client.get("/logout", follow_redirects=False)
    user_login = login(client, username="business", password="business-pass")
    assert user_login.status_code in (302, 303)

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Live OTP Dashboard" in dashboard.text
