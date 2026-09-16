import pyotp


def test_scoped_client_credential_can_only_read_granted_portal(client):
    from tests.conftest import csrf_token, login, step_up

    login(client)
    assert step_up(client).status_code == 200
    portal_secret = pyotp.random_base32()
    portal_response = client.post(
        "/admin/portals",
        data={
            "portal_name": "client-portal",
            "display_name": "Client Portal",
            "secret": portal_secret,
            "period": "30",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert portal_response.status_code in (302, 303)

    csrf = csrf_token(client, "/dashboard")
    client_response = client.post(
        "/api/v1/clients",
        json={"name": "a360-client", "environment": "test", "expires_in_days": 30},
        headers={"X-CSRF-Token": csrf},
    )
    assert client_response.status_code == 200
    client_id = client_response.json()["client_id"]

    credential_response = client.post(
        f"/api/v1/clients/{client_id}/credentials",
        json={"expires_in_days": 30},
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert credential_response.status_code == 200
    token = credential_response.json()["credential"]
    assert token.startswith("otp_")

    credentials = client.get(f"/api/v1/clients/{client_id}/credentials")
    assert credentials.status_code == 200
    credential_id = credentials.json()["credentials"][0]["id"]

    grant_response = client.post(
        f"/api/v1/clients/{client_id}/grants/client-portal",
        json={"expires_in_days": 30},
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert grant_response.status_code == 200

    otp_response = client.post(
        "/api/v1/portals/client-portal/otp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert otp_response.status_code == 200
    assert otp_response.json()["portal_name"] == "client-portal"
    assert token not in otp_response.text

    denied = client.post(
        "/api/v1/portals/not-granted/otp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 404

    revoke_credential_response = client.post(
        f"/api/v1/clients/{client_id}/credentials/{credential_id}/revoke",
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert revoke_credential_response.status_code == 200
    revoked = client.post(
        "/api/v1/portals/client-portal/otp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked.status_code == 401

    replacement = client.post(
        f"/api/v1/clients/{client_id}/credentials",
        json={"expires_in_days": 30},
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert replacement.status_code == 200
    revoke_response = client.post(
        f"/api/v1/clients/{client_id}/revoke",
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert revoke_response.status_code == 200
    repeated_revoke = client.post(
        f"/api/v1/clients/{client_id}/credentials/{credential_id}/revoke",
        headers={"X-CSRF-Token": csrf_token(client, "/dashboard")},
    )
    assert repeated_revoke.status_code == 404
