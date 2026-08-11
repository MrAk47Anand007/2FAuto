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
