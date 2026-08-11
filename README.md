# OTP Microservice

A production-ready TOTP (Time-based One-Time Password) microservice built with FastAPI.
Designed for internal use in RPA/automation scripts that need to automate 2FA login flows.
It also includes a private-network browser portal for business users who need
to view shared MFA codes without Postman or custom request headers.

---

## Features

- TOTP code generation and verification via `pyotp`
- Two-tier authentication: API key and HMAC request signing
- Replay-attack prevention (30-second signature window)
- Constant-time comparison everywhere to prevent timing attacks
- Structured request logging (method · path · status · latency)
- No stack traces exposed to clients
- Non-root Docker image
- Admin login for managing multiple portal TOTP secrets
- Business-user dashboard with multiple live OTP cards
- Per-portal API endpoint such as `/otp/vendor-login`
- Dashboard countdown refreshes locally and fetches new codes only when the MFA window changes

---

## Project Structure

```
otp-service/
├── app/
│   ├── main.py              # FastAPI app factory + middleware
│   ├── routes/
│   │   ├── auth.py          # /login, /logout
│   │   ├── admin.py         # /admin portal and user management
│   │   ├── ui.py            # /dashboard and dashboard JSON
│   │   └── otp.py           # /health, /otp, /otp/verify, /otp/secure, /otp/{portal}
│   ├── middleware/
│   │   └── auth.py          # API key + HMAC signature dependencies
│   └── core/
│       ├── config.py        # Settings loaded from .env (validates on startup)
│       ├── database.py      # SQLite users and portal secrets
│       ├── security.py      # Password hashing and signed browser sessions
│       └── totp.py          # TOTP generation / verification helpers
├── app/templates/           # Login, admin, and dashboard pages
├── app/static/              # CSS and dashboard refresh JavaScript
├── .env.example
├── requirements.txt
└── Dockerfile
```

---

## Setup

### 1. Copy and fill in environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
API_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">
OTP_SECRET=<generate: python -c "import pyotp; print(pyotp.random_base32())">
HOST=0.0.0.0
PORT=8000
ENABLE_DOCS=false   # set to true during development
DATABASE_PATH=otp_service.db
SESSION_SECRET=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<set a strong first admin password>
```

> **Important:** `API_KEY`, `SESSION_SECRET`, and `ADMIN_PASSWORD` are required.
> `OTP_SECRET` is optional for the new multi-portal UI, but keep it configured if
> existing automation still calls the legacy `/otp` endpoint. Each admin-added
> portal secret must be the same base32 secret registered in the related MFA system.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running Locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For development with auto-reload and Swagger UI, set `ENABLE_DOCS=true` in `.env` then:

```bash
uvicorn app.main:app --reload
# Swagger UI: http://localhost:8000/docs
```

---

## Browser Portal

### Admin

Open:

```text
http://localhost:8000/login
```

Sign in with `ADMIN_USERNAME` and `ADMIN_PASSWORD`. The admin account is created
automatically on first startup when it does not already exist in SQLite.

From `/admin`, an admin can:

- Add portal MFA secrets with a route name, display name, base32 secret, and MFA period.
- Create business users or additional admins.
- Disable or delete portal entries.

Portal route names must use lowercase letters, numbers, and hyphens, for example:

```text
vendor-login
bank
agency-portal
```

### Business users

Business users sign in at `/login` and land on:

```text
http://localhost:8000/dashboard
```

The dashboard shows all active portal OTPs like an authenticator app. It updates
the visible countdown in the browser, but it does not call the backend every
second. It fetches OTP data on page load, when the MFA/TOTP window rolls over,
and when the user clicks Refresh.

---

## Running with Docker

### Build

```bash
docker build -t otp-service .
```

### Run

```bash
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  otp-service
```

---

## API Reference

All protected endpoints require the `X-API-Key` header.
All error responses are JSON: `{"error": "message"}`.

### `GET /health` — public

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok", "timestamp": 1700000000}
```

---

### `GET /otp` — API-key protected

Returns the current legacy env-based TOTP code and how many seconds remain in the
30-second window. Keep `OTP_SECRET` configured if this endpoint is used.

```bash
curl http://localhost:8000/otp \
  -H "X-API-Key: your-api-key"
```

```json
{"otp": "482910", "valid_for_seconds": 18, "period": 30, "timestamp": 1700000012}
```

---

### `GET /otp/{portal_name}` — API-key protected

Returns the current TOTP for an admin-registered portal.

```bash
curl http://localhost:8000/otp/vendor-login \
  -H "X-API-Key: your-api-key"
```

```json
{
  "otp": "482910",
  "valid_for_seconds": 18,
  "period": 30,
  "timestamp": 1700000012,
  "portal_name": "vendor-login",
  "display_name": "Vendor Login"
}
```

---

### `POST /otp/verify` — API-key protected

Verify a TOTP code. Accepts ±1 window (90 s) for clock-skew tolerance.

```bash
curl -X POST http://localhost:8000/otp/verify \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"otp": "482910"}'
```

```json
{"valid": true, "timestamp": 1700000015}
```

---

### `GET /otp/secure` — API-key + HMAC signature

Extra layer for high-security callers. Requires three headers:

| Header | Value |
|---|---|
| `X-API-Key` | Your API key |
| `X-Timestamp` | Current Unix timestamp (integer string) |
| `X-Signature` | `HMAC-SHA256(key=API_KEY, msg=timestamp).hexdigest()` |

The server rejects requests where the timestamp is older than **30 seconds** (replay-attack prevention).

```bash
TIMESTAMP=$(date +%s)
SIGNATURE=$(echo -n "$TIMESTAMP" | openssl dgst -sha256 -hmac "your-api-key" | awk '{print $2}')

curl http://localhost:8000/otp/secure \
  -H "X-API-Key: your-api-key" \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Signature: $SIGNATURE"
```

---

## Client Examples

### Python — basic

```python
import requests

response = requests.get(
    "http://localhost:8000/otp",
    headers={"X-API-Key": "your-api-key"},
)
print(response.json())  # {"otp": "482910", "valid_for_seconds": 18, "timestamp": ...}
```

### Python — HMAC-signed request

```python
import hmac
import hashlib
import time
import requests

API_KEY = "your-api-key"
timestamp = str(int(time.time()))
signature = hmac.new(
    API_KEY.encode(),
    timestamp.encode(),
    hashlib.sha256,
).hexdigest()

response = requests.get(
    "http://localhost:8000/otp/secure",
    headers={
        "X-API-Key": API_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    },
)
print(response.json())
```

### Python — verify in an automation script

```python
import requests

def get_otp(api_key: str, base_url: str = "http://localhost:8000") -> str:
    resp = requests.get(f"{base_url}/otp", headers={"X-API-Key": api_key})
    resp.raise_for_status()
    return resp.json()["otp"]
```

---

## Security Notes

- **API key** is compared with `hmac.compare_digest()` to prevent timing attacks.
- **HMAC signature** uses SHA-256; requests older than 30 seconds are rejected to prevent replay attacks.
- **OTP_SECRET** and **API_KEY** are never logged or returned in any response.
- Admin-added TOTP secrets are masked in the UI after save and are not returned by dashboard JSON.
- Generated OTP codes are shown only to authenticated browser users or API callers with `X-API-Key`.
- **Stack traces** are never exposed; all unhandled errors return `{"error": "Internal server error"}`.
- The Docker image runs as a **non-root user** (`appuser`).
- Swagger UI (`/docs`) is **disabled by default**; enable only during development via `ENABLE_DOCS=true`.
- Use HTTPS (via a reverse proxy such as nginx or Caddy) in production.
