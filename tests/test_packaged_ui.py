from fastapi.testclient import TestClient

def test_packaged_ui_and_api_share_origin(client, tmp_path):
    from app.main import create_app

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><div id="app">2FAuto packaged</div></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "assets" / "app.js").write_text("window.twoFAuto = true;", encoding="utf-8")
    (tmp_path / "favicon.png").write_bytes(b"fake-icon")

    with TestClient(create_app(packaged_ui_dir=tmp_path)) as packaged:
        for path in ("/", "/login", "/app", "/app/admin/people"):
            response = packaged.get(path)
            assert response.status_code == 200
            assert "2FAuto packaged" in response.text

        asset = packaged.get("/assets/app.js")
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]
        assert packaged.get("/favicon.png?filename=index.html").content == b"fake-icon"

        assert packaged.get("/api/not-a-real-route").status_code == 404
        assert packaged.get("/api/v1/me").status_code == 401

        login = packaged.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"}
        )
        assert login.status_code == 200
        assert packaged.post("/api/v1/auth/logout").status_code == 403


def test_legacy_login_page_still_works(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "2FAuto packaged" not in response.text
