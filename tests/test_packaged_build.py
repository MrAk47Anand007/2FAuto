import subprocess
import sys
from pathlib import Path


def test_packaged_build_has_static_shell_and_assets(client, tmp_path):
    root = Path(__file__).resolve().parents[1]
    build = subprocess.run(
        [sys.executable, str(root / "scripts" / "build_packaged_ui.py"), "--output", str(tmp_path)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    shell = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<html" in shell
    assert "/assets/" in shell
    assert list((tmp_path / "assets").glob("*.js"))
    assert not (tmp_path / "server").exists()

    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app(packaged_ui_dir=tmp_path)) as packaged:
        page = packaged.get("/app/portals")
        assert page.status_code == 200
        assert "/assets/" in page.text
        assert "2FAuto" in page.text
        asset_path = page.text.split('src="/assets/', 1)[1].split('"', 1)[0]
        assert packaged.get(f"/assets/{asset_path}").status_code == 200
