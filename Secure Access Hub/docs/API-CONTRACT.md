# 2FAuto frontend ↔ FastAPI contract

This frontend calls the backend with **relative URLs** and `credentials: "include"`,
so the `otp_session` HttpOnly cookie travels on every request and React never reads it.
All mutations send `X-CSRF-Token` (and, for the legacy form endpoints, a `csrf_token`
form field). The CSRF token is obtained from `GET /api/v1/me` and held in memory only.

## Already existing (used as-is)

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/v1/me/step-up` | form `password`; returns `{step_up, valid_for_seconds}` |
| GET | `/api/v1/me/sessions` | `{sessions:[...]}` |
| DELETE | `/api/v1/me/sessions/{id}` | CSRF |
| GET | `/api/ui/portals` | authorized portal metadata |
| POST | `/api/ui/portals/{portal}/otp` | called only on explicit Reveal |
| POST | `/admin/portals` · `/edit` · `/disable` · `/reactivate` · `/delete` | URL-encoded form, 303 → `/admin` |
| POST | `/admin/portals/{portal}/grants` · `/grants/{user}/revoke` | URL-encoded form |
| POST | `/admin/users` · `/users/{user}/disable` · `/reactivate` | URL-encoded form |
| POST | `/admin/teams` · `/members` · `/members/remove` · `/grants/{portal}` · `/grants/{portal}/revoke` | URL-encoded form |
| GET | `/admin/api/v1/audit?limit=` | recent-event feed, 1–500 |
| GET/POST | `/api/v1/clients`, `/clients/{id}/credentials`, `/credentials/{cid}/revoke`, `/grants/{portal}`, `/revoke` | JSON |

`/api/ui/otps` (410) is never called.

303 responses from the legacy form handlers are followed and treated as success;
the HTML body is ignored. No Jinja HTML is ever scraped.

## Required backend additions (not yet implemented)

These are the only new routes the SPA needs. Each must reuse the existing
authentication, CSRF, origin validation, step-up, audit, and throttling
dependencies — no new auth mechanism, no JWT.

### 1. `GET /api/v1/me`
Session bootstrap. `Cache-Control: no-store`. 401 when unauthenticated.
```json
{ "id": 3, "username": "anand", "role": "admin",
  "csrf_token": "...", "session_expires_at": 1757000000,
  "step_up_expires_at": 1756999700 }
```
Must not return password hashes or raw session tokens, and must not extend
session lifetime (bootstrap is a read, not activity).

### 2. `POST /api/v1/auth/login`
JSON body `{username, password}`. Reuses the existing credential check, cookie
issue, session creation, audit entry, and login throttling. Returns
`{id, username, role, csrf_token}` on success and JSON `{"detail": "..."}` with
401 on failure/throttle (the frontend reports both as "incorrect credentials or
too many attempts"). The current CSRF dependency special-cases `/login` only —
`/api/v1/auth/login` needs an explicit decision: keep origin validation, exempt
it from session-CSRF (there is no session yet), and rely on the same-origin
check plus throttling.

### 3. `POST /api/v1/auth/logout`
Requires session **and** CSRF validation. Revokes the session, clears the
cookie, returns JSON (not a 303).

### 4. `GET /admin/api/v1/admin/portals` · `/users` · `/teams`
Admin-only JSON listings backed by the same services the Jinja pages use:
```json
{"portals":[{"portal_name":"vendor-login","display_name":"Vendor Login","period":30,
  "status":"active","grants":[{"username":"jo","expires_at":1760000000,"source":"direct"},
                              {"username":"sam","expires_at":null,"source":"team","team_name":"ops"}]}]}
{"users":[{"id":1,"username":"jo","role":"user","status":"active","created_at":"…","last_login_at":"…"}]}
{"teams":[{"name":"ops","members":["jo"],"grants":[{"portal_name":"vendor-login","expires_at":null}]}]}
```
The `source` / `team_name` fields are what let the UI distinguish direct access
from inherited team access.

### 5. Optional: client access visibility
`GET /api/v1/clients/{id}/grants` and
`POST /api/v1/clients/{id}/grants/{portal}/revoke` (admin + CSRF + step-up + audit).
Until these exist the Automation Clients screen states plainly that per-client
granted portals cannot be listed and only whole-client revocation is offered.

## Error conventions handled

`{"detail": "..."}`, FastAPI validation arrays, `{"error": "..."}`, HTML 401s,
and empty bodies are all normalized into a typed `ApiError`
(`status`, `kind`, `message`, `fieldErrors`, `retryAfterSeconds`).
428 opens the step-up dialog; 429 surfaces `Retry-After`; 403 is reported as
access denied, never as "sign in again".

## Running the frontend against the local FastAPI backend

The Vite dev server includes a dev-only backend bridge (`vite.config.ts`) that
forwards `/api/*`, `/admin/*`, `/health` and `/ready` to `VITE_BACKEND_ORIGIN`
(default `http://localhost:8000`). It is connect middleware rather than
`server.proxy` so it also works in environments that strip proxy config.

- The browser's `Origin` header is forwarded unchanged — configure FastAPI to
  allow the dev origin explicitly. Never allow `*` or `null`, and do not
  disable CSRF for development.
- `Set-Cookie` from the backend is passed through, so the HttpOnly
  `otp_session` cookie is set on the single dev origin. React never reads it.
- Responses carry `Referrer-Policy: same-origin`, matching production.
- `/login` and `/logout` are NOT forwarded: `/login` is the SPA login route and
  the app authenticates through `POST /api/v1/auth/login|logout`. The legacy
  Jinja pages remain reachable directly on the backend during migration.

Dev: run FastAPI on :8000, then `bun run dev` (or `npm run dev`).
Production: build with `bun run build` and serve the built client from the
same origin as FastAPI, with an SPA fallback scoped to `/app/*` only — the
fallback must never answer `/api/*` (missing API paths must still 404 as JSON).

### Verification status

Type checking, linting and the production build pass. All eight screens were
exercised in a real browser (desktop 1280px and mobile 390px): login, portals
with reveal/hide/copy and an expiry countdown, sessions, admin portals, people,
teams, automation clients, audit. That browser run used a local stand-in server
implementing the documented JSON contracts, because the real FastAPI instance
runs on your machine. Re-run the same flows against the real backend after the
four added endpoint groups above are implemented; login throttling, step-up and
audit writes can only be confirmed there.
