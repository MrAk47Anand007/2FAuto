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
    executable = (runtime_dir / executable_name if onefile else
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
                    assert json.load(response)["configured"] is False
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
    finally:
        process.terminate()
        process.wait(timeout=10)
