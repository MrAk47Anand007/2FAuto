import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


def test_role_config_accepts_local_roles_and_rejects_unsafe_values(tmp_path):
    from app.runtime.config import RuntimeConfig, RuntimeConfigError

    for role in ("server", "desktop-web"):
        config = RuntimeConfig.from_mapping({
            "version": 1, "role": role, "host": "127.0.0.1", "port": 8765,
            "data_dir": str(tmp_path / role),
        })
        assert config.role == role
        assert config.database_path == tmp_path / role / "otp_service.db"

    invalid = [
        {"version": 2}, {"role": "client"}, {"host": "0.0.0.0"},
        {"host": "192.0.2.10"}, {"port": 0}, {"port": 70000},
        {"data_dir": "relative/path"}, {"role": []}, {"host": []},
    ]
    valid = {"version": 1, "role": "server", "host": "127.0.0.1", "port": 8765,
             "data_dir": str(tmp_path / "vault")}
    for change in invalid:
        with pytest.raises(RuntimeConfigError):
            RuntimeConfig.from_mapping({**valid, **change})


def test_config_file_and_single_instance_lock(tmp_path):
    from app.runtime.config import RuntimeConfig, RuntimeConfigError, write_config
    from app.runtime.lock import instance_lock

    directory = tmp_path / "vault"
    config_path = write_config(directory, role="desktop-web", port=8765)
    assert json.loads(config_path.read_text(encoding="utf-8"))["role"] == "desktop-web"
    assert RuntimeConfig.load(config_path).data_dir == directory
    with instance_lock(directory):
        with pytest.raises(RuntimeConfigError, match="already running"):
            with instance_lock(directory):
                pass


def test_occupied_port_is_rejected(tmp_path):
    from app.runtime.config import RuntimeConfig, RuntimeConfigError
    from app.runtime.lock import ensure_port_available

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        config = RuntimeConfig.from_mapping({
            "version": 1, "role": "server", "host": "127.0.0.1", "port": port,
            "data_dir": str(tmp_path / "vault"),
        })
        with pytest.raises(RuntimeConfigError, match="port"):
            ensure_port_available(config)


def test_runtime_serves_setup_and_rejects_second_writer(tmp_path):
    from app.runtime.config import write_config

    root = Path(__file__).resolve().parents[1]
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html>runtime shell</html>", encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config_path = write_config(tmp_path / "vault", role="desktop-web", port=port)
    command = [sys.executable, "-m", "app.runtime.entry", "serve", "--config",
               str(config_path), "--ui-dir", str(ui_dir)]
    runtime_env = {**os.environ, "PYTHONPATH": str(root)}

    process = subprocess.Popen(command, cwd=tmp_path, env=runtime_env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/setup/status", timeout=1) as response:
                    assert json.load(response)["configured"] is False
                    break
            except (OSError, ConnectionError):
                if process.poll() is not None:
                    pytest.fail(f"Runtime exited early: {process.stdout.read()}")
                time.sleep(0.2)
        else:
            pytest.fail("Runtime did not become available")

        second = subprocess.run(command, cwd=tmp_path, env=runtime_env,
                                capture_output=True, text=True, timeout=10)
        assert second.returncode == 2
        assert "already running" in (second.stdout + second.stderr)
    finally:
        process.terminate()
        process.wait(timeout=10)

    restarted = subprocess.Popen(command, cwd=tmp_path, env=runtime_env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/setup/status", timeout=1) as response:
                    assert response.status == 200
                    break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("Runtime did not restart")
    finally:
        restarted.terminate()
        restarted.wait(timeout=10)
