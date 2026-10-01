def test_health_includes_content_security_policy(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert "content-security-policy" in {
        name.lower() for name in response.headers.keys()
    }


def test_legacy_api_rate_limit_returns_429(client, monkeypatch):
    from app.core import config

    config.settings.LEGACY_API_RATE_LIMIT_PER_MINUTE = 2
    headers = {"X-API-Key": "test-api-key"}

    assert client.get("/otp", headers=headers).status_code == 200
    assert client.get("/otp", headers=headers).status_code == 200
    limited = client.get("/otp", headers=headers)
    assert limited.status_code == 429
    assert limited.headers.get("retry-after") == "60"
