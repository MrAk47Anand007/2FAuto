"""Exercise first-run setup of an installed, loopback-only Server service."""

import json
import secrets
import urllib.request


BASE = "http://127.0.0.1:8765"


def read(path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return response.status, json.load(response)


def main() -> None:
    status_code, status = read("/api/setup/status")
    if status_code != 200 or status.get("configured") is not False:
        raise RuntimeError("Server did not start in first-run setup mode")
    token = status.get("setup_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Local setup token is missing")
    request = urllib.request.Request(
        BASE + "/api/setup/initialize",
        data=json.dumps({
            "username": "ci_owner",
            "password": secrets.token_urlsafe(32),
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Setup-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 201:
            raise RuntimeError("First administrator setup failed")
    ready_code, ready = read("/ready")
    if ready_code != 200 or ready.get("status") != "ready":
        raise RuntimeError("Installed Server is not ready after setup")
    print("Installed Server setup and readiness passed")


if __name__ == "__main__":
    main()
