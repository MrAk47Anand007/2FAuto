"""A360 helper that retrieves one granted OTP without accepting a seed."""

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get_totp(portal_name: str, base_url: str, client_token: str) -> str:
    url = f"{base_url.rstrip('/')}/api/v1/portals/{portal_name}/otp"
    request = Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {client_token}",
            "Accept": "application/json",
            "Cache-Control": "no-store",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("OTP service request failed") from exc
    otp = payload.get("otp")
    if not isinstance(otp, str) or not otp.isdigit():
        raise RuntimeError("OTP service returned an invalid code")
    return otp


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python totp_a360.py PORTAL_NAME")
    token = os.getenv("OTP_CLIENT_TOKEN")
    if not token:
        raise SystemExit("OTP_CLIENT_TOKEN must be supplied by the automation credential store")
    print(
        get_totp(
            sys.argv[1],
            os.getenv("OTP_SERVICE_URL", "http://localhost:8000"),
            token,
        )
    )
