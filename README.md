# OTP Microservice

A production-ready TOTP (Time-based One-Time Password) microservice built with FastAPI.
Designed for internal use in RPA/automation scripts that need to automate 2FA login flows.

---

## Features

- TOTP code generation and verification via `pyotp`
- Two-tier authentication: API key and HMAC request signing
- Replay-attack prevention (30-second signature window)
- Constant-time comparison everywhere to prevent timing attacks
- Structured request logging (method · path · status · latency)
- No stack traces exposed to clients
- Non-root Docker image

---

## Project Structure

```
otp-service/
├── app/
│   ├── main.py              # FastAPI app factory + middleware
│   ├── routes/
│   │   └── otp.py           # /health, /otp, /otp/verify, /otp/secure
│   ├── middleware/
│   │   └── auth.py          # API key + HMAC signature dependencies
│   └── core/
│       ├── config.py        # Settings loaded from .env (validates on startup)
│       └── totp.py          # TOTP generation / verification helpers
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
```

> **Important:** `OTP_SECRET` must be the same base32 secret registered in your authenticator
> app (Google Authenticator, Authy, etc.). The service will exit at startup if either
> `API_KEY` or `OTP_SECRET` is missing or if the secret is not a valid base32 string.

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

Returns the current TOTP code and how many seconds remain in the 30-second window.

```bash
curl http://localhost:8000/otp \
  -H "X-API-Key: your-api-key"
```

```json
{"otp": "482910", "valid_for_seconds": 18, "timestamp": 1700000012}
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
- **Stack traces** are never exposed; all unhandled errors return `{"error": "Internal server error"}`.
- The Docker image runs as a **non-root user** (`appuser`).
- Swagger UI (`/docs`) is **disabled by default**; enable only during development via `ENABLE_DOCS=true`.
- Use HTTPS (via a reverse proxy such as nginx or Caddy) in production.
