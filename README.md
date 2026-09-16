# 2FAuto — OTP Microservice

A TOTP (Time-based One-Time Password) microservice built with FastAPI for
internal testing and RPA/automation scripts that need to automate 2FA login flows.
It also includes a private-network browser portal for business users who need
to view shared MFA codes without Postman or custom request headers, plus a small
command-line helper for Automation Anywhere A360.

---

## Features

- TOTP code generation and verification via `pyotp`
- Scoped bearer credentials for automation, with legacy global-key compatibility disabled by default
- Opaque, revocable browser sessions with CSRF and same-origin protection
- HMAC request timestamp freshness check (30-second window; reuse within that window is possible)
- Environment-aware startup checks and security response headers
- Constant-time comparison everywhere to prevent timing attacks
- Structured request logging (method · path · status · latency)
- No stack traces exposed to clients
- Non-root Docker image
- Admin login for managing multiple portal TOTP secrets
- Role-based access for administrators and business users
- SQLite persistence for users and portal configuration
- Business-user dashboard with multiple live OTP cards
- Per-portal scoped API endpoint such as `/api/v1/portals/vendor-login/otp`
- Dashboard countdowns refresh locally after an explicit reveal and hide codes at expiry
- A360-compatible `totp_a360.py` command-line helper

---

## Project Structure

```
2FAuto/
├── app/
│   ├── main.py              # FastAPI app factory + middleware
│   ├── routes/
│   │   ├── auth.py          # /login, /logout
│   │   ├── admin.py         # /admin portal and user management
│   │   ├── ui.py            # /dashboard and authorized dashboard JSON
│   │   ├── clients.py       # scoped automation clients and credentials
│   │   └── otp.py           # /health, /otp, /otp/verify, /otp/secure, /otp/{portal}
│   ├── middleware/
│   │   └── auth.py          # API key + HMAC signature dependencies
│   └── core/
│       ├── config.py        # Settings loaded from .env (validates on startup)
│       ├── database.py      # SQLite users and portal secrets
│       ├── security.py      # Password hashing, opaque sessions, and CSRF
│       └── totp.py          # TOTP generation / verification helpers
├── app/templates/           # Login, admin, and dashboard pages
├── app/static/              # CSS and dashboard refresh JavaScript
├── tests/                   # API, authentication, authorization, portal, and client tests
├── docs/superpowers/plans/   # Multi-user portal implementation plan
├── .env.example
├── requirements.txt
├── Dockerfile
└── totp_a360.py             # Standalone A360 command-line helper
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
# Optional: required only when legacy /otp or /otp/verify is used
OTP_SECRET=<generate: python -c "import pyotp; print(pyotp.random_base32())">
APP_ENV=development
HOST=0.0.0.0
PORT=8000
ENABLE_DOCS=false   # set to true during development
COOKIE_SECURE=false # set to true behind HTTPS in production
SECRET_ENCRYPTION_KEY=<generate a URL-safe base64 32-byte key>
SECRET_ENCRYPTION_KEY_VERSION=v1
SECRET_ENCRYPTION_KEYS= # optional old-version map during rotation
LEGACY_API_ENABLED=false # temporary compatibility for old global-key clients
DATABASE_PATH=otp_service.db
SESSION_SECRET=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<set a strong first admin password>
```

> **Important:** `SESSION_SECRET`, `ADMIN_PASSWORD`, and
> `SECRET_ENCRYPTION_KEY` are required. `API_KEY` is required only while the
> temporary `LEGACY_API_ENABLED` compatibility mode is enabled.
> `OTP_SECRET` is optional for the new multi-portal UI, but keep it configured if
> existing automation still calls the legacy `/otp` endpoint. Each admin-added
> portal secret must be the same base32 secret registered in the related MFA system.
> In `APP_ENV=production`, startup rejects sample credentials, enabled API docs,
> and `COOKIE_SECURE=false`.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

For an isolated local setup:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 3. Run the test suite

```bash
python -m pytest -q
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

Each portal can use an MFA period between 10 and 120 seconds. The secret is
validated as a Base32 TOTP secret before it is saved, and the admin page only
shows encrypted-at-rest status after saving. Administrators can also create or disable
additional `admin` and `user` accounts, grant portal access to users or teams, and
manage scoped automation clients. The final active administrator cannot be disabled.

### Business users

Business users sign in at `/login` and land on:

```text
http://localhost:8000/dashboard
```

The dashboard shows only portals explicitly granted to the signed-in user. It
loads portal metadata without codes; a user must explicitly reveal one portal at
a time. Revealed codes are held in transient page memory, hidden when their
window ends, and never written to browser storage.

Browser sessions use opaque server-side records with hashed token verifiers,
15-minute idle expiry, 8-hour absolute expiry, revocation, `HttpOnly`,
`SameSite=Lax`, and configurable `Secure` cookies. State-changing browser
requests require a CSRF token and same-origin checks.
Sensitive portal/grant/client operations require a password step-up that is
fresh for five minutes. Independent MFA/SSO is still required before broad
production release.

### Portal preview

The screenshots below use fictional provider names and test-only OTP secrets.

![Business-user dashboard with active OTP cards](https://raw.githubusercontent.com/MrAk47Anand007/2FAuto/main/docs/assets/otp-server-demo/business-dashboard.png)

![Admin console for managing portals and users](https://raw.githubusercontent.com/MrAk47Anand007/2FAuto/main/docs/assets/otp-server-demo/admin-console.png)

For a business-friendly walkthrough and RPA integration examples, see the
[OTP Portal User Guide](docs/OTP-PORTAL-USER-GUIDE.md).

### A360 command-line helper

`totp_a360.py` asks the scoped API for one granted portal code so Automation
Anywhere A360 can capture it from standard output. The client credential must
come from the automation platform's secure credential store; no seed is passed
as a process argument:

```bash
OTP_SERVICE_URL=http://localhost:8000 OTP_CLIENT_TOKEN=one-time-client-token \
  python totp_a360.py vendor-login
```

The helper preserves the OTP as a string, including leading zeroes, and
requires the FastAPI service to be running.

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

The SQLite database is inside the container by default. Mount a volume or set
`DATABASE_PATH` to a mounted path when portal users and secrets must survive
container replacement.

---

## API Reference

New machine-to-machine OTP access uses scoped bearer credentials. The old
global-key machine endpoints are available only when `LEGACY_API_ENABLED=true`
and are intended only for time-boxed migration compatibility.
The browser portal uses the `otp_session` cookie. All error responses from the API
are JSON. Request and authentication errors use FastAPI's `detail` field;
unexpected server errors return `{"error": "Internal server error"}`.

| Endpoint | Authentication | Purpose |
|---|---|---|
| `GET /health` | Public | Health check |
| `GET /ready` | Public | Readiness check |
| `GET /otp` | Legacy `X-API-Key` | Legacy env-based OTP; disabled by default |
| `GET /otp/{portal_name}` | Legacy `X-API-Key` | Active portal OTP; disabled by default |
| `POST /otp/verify` | Legacy `X-API-Key` | Verify the legacy OTP; disabled by default |
| `GET /otp/secure` | Legacy `X-API-Key` + HMAC | Signed legacy OTP request; disabled by default |
| `GET /api/v1/me/sessions` | Browser session | List the signed-in user's sessions |
| `GET /api/ui/portals` | Browser session | Authorized portal metadata only |
| `POST /api/ui/portals/{portal_name}/otp` | Browser session + CSRF | Explicitly reveal one authorized OTP |
| `POST /api/v1/portals/{portal_name}/otp` | Scoped bearer credential | Client-granted portal OTP |

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

Unknown or disabled portal names return `404`.

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

The server rejects requests whose timestamp is more than **30 seconds** away from
the server clock. This limits the freshness window but does not prevent replay
of the same signed request within that window.

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

### Python — scoped client credential

```python
import requests

CLIENT_TOKEN = "one-time-client-token"
response = requests.post(
    "http://localhost:8000/api/v1/portals/vendor-login/otp",
    headers={"Authorization": f"Bearer {CLIENT_TOKEN}"},
)
response.raise_for_status()
print(response.json()["otp"])
```

The token is returned once when an administrator creates a credential. Store it
in the automation platform's protected credential store and grant the client
only the portals it needs.

### Python — legacy compatibility example

The old global-key examples below apply only while `LEGACY_API_ENABLED=true`.
Plan to migrate each consumer to a scoped client before disabling compatibility.

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

### Browser dashboard data

After signing in at `/login`, the dashboard requests:

```text
GET /api/ui/portals
```

The response contains only active portal names, display names, and periods. To
reveal a code, the browser sends a CSRF-protected `POST` to
`/api/ui/portals/{portal_name}/otp`. The retired `/api/ui/otps` bulk endpoint
returns `410 Gone`.

---

## Security Notes

- **Legacy API keys** are compared with `hmac.compare_digest()` and are disabled by default.
- **Legacy HMAC signatures** use SHA-256; requests outside the 30-second freshness window are rejected. There is no nonce store yet, so reuse within that window remains possible.
- **OTP_SECRET** and **API_KEY** are never logged or returned in any response.
- Admin-added TOTP secrets are represented only by encrypted-at-rest status in the UI and are not returned by dashboard JSON.
- Portal secrets are encrypted with AES-GCM before storage in the configured SQLite database. Keep the encryption key outside the database and protect both the key provider and database backups.
- Generated OTP codes are shown only to authorized browser users or scoped bearer clients. Legacy `X-API-Key` callers are accepted only in explicit compatibility mode.
- Browser login cookies are opaque, `HttpOnly`, `SameSite=Lax`, revocable, and expire after idle/absolute session limits. Set `COOKIE_SECURE=true` behind HTTPS.
- **Stack traces** are never exposed; all unhandled errors return `{"error": "Internal server error"}`.
- The Docker image runs as a **non-root user** (`appuser`).
- Swagger UI (`/docs`) is **disabled by default**; enable only during development via `ENABLE_DOCS=true`.
- Use HTTPS (via a reverse proxy such as nginx or Caddy) in production.
