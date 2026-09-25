"""Opt-in smoke test for a freshly built PyInstaller runtime."""

import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest


@pytest.mark.parametrize("onefile", [False, True])
def test_frozen_runtime_serves_bundled_ui_without_developer_paths(tmp_path, onefile):
    executable_name = "2fauto-runtime.exe" if os.name == "nt" else "2fauto-runtime"
    runtime_dir = Path(__file__).resolve().parents[1] / "build" / "runtime"
    packaged_name = "twofauto-runtime.exe" if os.name == "nt" else "twofauto-runtime"
    executable = ((runtime_dir / packaged_name if (runtime_dir / packaged_name).is_file()
                   else runtime_dir / executable_name) if onefile else
                  runtime_dir / "2fauto-runtime" / executable_name)
    if not executable.exists():
        pytest.skip("Build with python scripts/build_runtime.py before this smoke test")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("NODE_PATH", None)
    if os.name == "nt":
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    vault = tmp_path / "vault"
    init = subprocess.run([str(executable), "init", "--role", "desktop-web", "--data-dir",
                           str(vault), "--port", str(port)], cwd=tmp_path, env=environment,
                          capture_output=True, text=True, timeout=20)
    assert init.returncode == 0, init.stdout + init.stderr

    process = subprocess.Popen([str(executable), "serve", "--config", str(vault / "runtime.json")],
                               cwd=tmp_path, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/setup/status", timeout=1) as response:
                    status = json.load(response)
                    assert status["configured"] is False
                    setup_token = status["setup_token"]
                    break
            except OSError:
                if process.poll() is not None:
                    pytest.fail(f"Frozen runtime exited early: {process.stdout.read()}")
                time.sleep(0.2)
        else:
            pytest.fail("Frozen runtime did not start")

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/setup", timeout=2) as response:
            page = response.read().decode("utf-8")
            assert "2FAuto" in page
            asset = re.search(r'src="(/assets/[^\"]+\.js)"', page)
            assert asset is not None
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{asset.group(1)}", timeout=2) as response:
            assert response.status == 200

        setup = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/setup/initialize",
            data=json.dumps({"username": "owner", "password": "correct horse battery staple"}).encode(),
            headers={"Content-Type": "application/json", "X-Setup-Token": setup_token},
            method="POST",
        )
        with urllib.request.urlopen(setup, timeout=5) as response:
            assert response.status == 201
        archive = tmp_path / "recovery.2fauto"
        backup = subprocess.run([str(executable), "backup", "--config", str(vault / "runtime.json"),
                                 "--output", str(archive)], cwd=tmp_path, env=environment,
                                input="a long recovery passphrase\n", capture_output=True,
                                text=True, timeout=30)
        assert backup.returncode == 0, backup.stdout + backup.stderr
        assert archive.is_file()
    finally:
        if os.name == "nt" and onefile:
            # PyInstaller's one-file launcher owns a child process that keeps
            # the executable locked if only the launcher is terminated.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        else:
            process.terminate()
        process.wait(timeout=10)

    restored = tmp_path / "new-vault"
    init_restored = subprocess.run([str(executable), "init", "--role", "desktop-web",
                                    "--data-dir", str(restored), "--port", str(port)],
                                   cwd=tmp_path, env=environment, capture_output=True,
                                   text=True, timeout=20)
    assert init_restored.returncode == 0, init_restored.stdout + init_restored.stderr
    recovered = subprocess.run([str(executable), "restore", "--config", str(restored / "runtime.json"),
                                "--input", str(archive)], cwd=tmp_path, env=environment,
                               input="a long recovery passphrase\n", capture_output=True,
                               text=True, timeout=30)
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert (restored / "otp_service.db").is_file()
    assert (restored / "vault-keys.bin").is_file()
