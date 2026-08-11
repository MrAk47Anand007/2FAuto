# Multi-User OTP Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the single-secret OTP microservice into a private-network multi-user OTP portal with admin-managed MFA secrets and a Google Authenticator-style live dashboard for business users.

**Architecture:** Keep FastAPI as the single app. Add SQLite persistence for users, portal secrets, and sessions; add server-rendered HTML/CSS/JS pages for login, admin management, and user dashboard; keep the existing automation API shape while adding per-portal OTP endpoints. The dashboard countdown updates in the browser, but OTP data is fetched only when the current TOTP/MFA time window changes.

**Tech Stack:** FastAPI, pyotp, SQLite, standard-library sqlite3, passlib[bcrypt] or bcrypt for password hashing, itsdangerous or signed cookie sessions, Jinja2 templates or FastAPI HTMLResponse, pytest + TestClient.

## Global Constraints

- Existing `/health`, `/otp`, `/otp/verify`, and `/otp/secure` must keep working during migration.
- Business users must not need Postman, custom headers, or manual API-key handling.
- Admin users can add, edit, disable, and delete OTP portal secrets from the UI.
- User dashboard must show multiple portal OTPs live, similar to Google Authenticator.
- The frontend must not poll every second for OTP. It may update countdown locally every second and fetch the next OTP only at the MFA window rollover.
- Default TOTP interval is 30 seconds unless a stored portal entry explicitly sets a different period.
- Private-network deployment is assumed, but admin and user login are still required.
- Do not log OTP secrets, passwords, generated OTP codes, or session cookie values.

---

## File Structure

- Modify `requirements.txt`: add password hashing, template/session/test dependencies.
- Modify `.env.example`: add `DATABASE_PATH`, `SESSION_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and optional `SECRET_ENCRYPTION_KEY`.
- Modify `app/core/config.py`: load new settings and keep backward compatibility with `OTP_SECRET`.
- Create `app/core/database.py`: SQLite connection, schema creation, and row helpers.
- Create `app/core/security.py`: password hashing, password verification, signed session helpers.
- Modify `app/core/totp.py`: support TOTP generation from a supplied secret and portal metadata.
- Create `app/models.py`: small dataclasses or Pydantic models for users and OTP entries.
- Create `app/routes/auth.py`: login, logout, current session dependencies.
- Create `app/routes/admin.py`: admin UI and API routes for managing portals and users.
- Create `app/routes/ui.py`: business-user dashboard and JSON data endpoints.
- Modify `app/routes/otp.py`: add `/otp/{portal_name}` while preserving existing endpoints.
- Modify `app/main.py`: initialize database on startup, include new routers, serve static assets.
- Create `app/templates/*.html`: base, login, dashboard, admin pages.
- Create `app/static/styles.css`: restrained dashboard and admin UI styling.
- Create `app/static/dashboard.js`: local countdown and window-based OTP refresh.
- Create `tests/`: auth, database, admin, OTP, and UI endpoint tests.

---

### Task 1: Persistence Foundation

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `app/core/config.py`
- Create: `app/core/database.py`
- Create: `app/models.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Produces: `init_database() -> None`
- Produces: `get_db() -> sqlite3.Connection`
- Produces: `create_user(username: str, password_hash: str, role: str) -> int`
- Produces: `get_user_by_username(username: str) -> dict | None`
- Produces: `create_otp_entry(portal_name: str, display_name: str, secret: str, period: int, created_by: int) -> int`
- Produces: `list_active_otp_entries() -> list[dict]`

- [ ] Add dependencies: `jinja2`, `python-multipart`, `bcrypt`, `itsdangerous`, `pytest`, `httpx`.
- [ ] Add env settings: `DATABASE_PATH=otp_service.db`, `SESSION_SECRET=change-me`, `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=change-me`.
- [ ] Write tests proving tables are created: `users`, `otp_entries`, and `sessions` if server-side sessions are used.
- [ ] Implement SQLite schema with unique `users.username` and unique `otp_entries.portal_name`.
- [ ] Store OTP entries with `portal_name`, `display_name`, `secret`, `period`, `is_active`, timestamps, and `created_by`.
- [ ] Run `pytest tests/test_database.py -v`.
- [ ] Commit: `feat: add sqlite persistence foundation`.

### Task 2: Authentication And Roles

**Files:**
- Create: `app/core/security.py`
- Create: `app/routes/auth.py`
- Modify: `app/main.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `get_user_by_username(username: str) -> dict | None`
- Produces: `hash_password(password: str) -> str`
- Produces: `verify_password(password: str, password_hash: str) -> bool`
- Produces: `create_session_cookie(user_id: int, role: str) -> str`
- Produces: `require_user(request: Request) -> dict`
- Produces: `require_admin(request: Request) -> dict`

- [ ] Write tests for password hashing and failed password verification.
- [ ] Write tests for `/login` accepting valid credentials and rejecting invalid credentials.
- [ ] Write tests that admin-only routes reject normal users.
- [ ] Implement signed cookie sessions with `SESSION_SECRET`.
- [ ] Bootstrap the admin account from env on startup if it does not exist.
- [ ] Implement `/login` and `/logout`.
- [ ] Run `pytest tests/test_auth.py -v`.
- [ ] Commit: `feat: add login and role-based sessions`.

### Task 3: Multi-Secret TOTP Core

**Files:**
- Modify: `app/core/totp.py`
- Modify: `app/routes/otp.py`
- Test: `tests/test_totp_multi_secret.py`

**Interfaces:**
- Consumes: `list_active_otp_entries() -> list[dict]`
- Produces: `get_otp_for_secret(secret: str, period: int = 30) -> dict`
- Produces: `verify_otp_for_secret(secret: str, code: str, period: int = 30) -> bool`
- Produces: `GET /otp/{portal_name}`

- [ ] Write tests for generating OTP from two different secrets.
- [ ] Write tests for `valid_for_seconds` respecting each entry period.
- [ ] Write tests for `GET /otp/{portal_name}` returning the matching portal OTP.
- [ ] Keep legacy `GET /otp` using the env `OTP_SECRET` when present.
- [ ] Return 404 for unknown or disabled portal names.
- [ ] Run `pytest tests/test_totp_multi_secret.py -v`.
- [ ] Commit: `feat: support per-portal otp generation`.

### Task 4: Admin Portal Management UI

**Files:**
- Create: `app/routes/admin.py`
- Create: `app/templates/base.html`
- Create: `app/templates/admin.html`
- Create: `app/static/styles.css`
- Modify: `app/main.py`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `require_admin(request: Request) -> dict`
- Consumes: `create_otp_entry(...) -> int`
- Produces: `GET /admin`
- Produces: `POST /admin/portals`
- Produces: `POST /admin/portals/{portal_name}/disable`
- Produces: `POST /admin/portals/{portal_name}/delete`

- [ ] Write tests that unauthenticated users cannot access `/admin`.
- [ ] Write tests that admin can create a portal secret with a valid base32 secret.
- [ ] Write tests that duplicate `portal_name` is rejected.
- [ ] Build admin page with a portal list and add-secret form.
- [ ] Validate `portal_name` as lowercase letters, numbers, and hyphens only.
- [ ] Never render the full stored secret after save; show only a masked form such as `ABCD...WXYZ`.
- [ ] Run `pytest tests/test_admin_routes.py -v`.
- [ ] Commit: `feat: add admin portal management`.

### Task 5: Business User Dashboard

**Files:**
- Create: `app/routes/ui.py`
- Create: `app/templates/dashboard.html`
- Create: `app/static/dashboard.js`
- Modify: `app/static/styles.css`
- Modify: `app/main.py`
- Test: `tests/test_ui_dashboard.py`

**Interfaces:**
- Consumes: `require_user(request: Request) -> dict`
- Consumes: `list_active_otp_entries() -> list[dict]`
- Consumes: `get_otp_for_secret(secret: str, period: int = 30) -> dict`
- Produces: `GET /dashboard`
- Produces: `GET /api/ui/otps`

- [ ] Write tests that unauthenticated users cannot access `/dashboard`.
- [ ] Write tests that `/api/ui/otps` returns all active portal OTP cards without secrets.
- [ ] Build dashboard page with multiple OTP tiles: display name, portal name, code, countdown, and status.
- [ ] Implement `dashboard.js` so it fetches `/api/ui/otps` on page load.
- [ ] Implement local countdown tick every second based on `timestamp`, `period`, and `valid_for_seconds`.
- [ ] Implement next backend fetch only when the shortest visible OTP reaches the next MFA rollover.
- [ ] Add a manual refresh button for users when they suspect clock drift.
- [ ] Run `pytest tests/test_ui_dashboard.py -v`.
- [ ] Commit: `feat: add live business otp dashboard`.

### Task 6: User Management

**Files:**
- Modify: `app/core/database.py`
- Modify: `app/routes/admin.py`
- Modify: `app/templates/admin.html`
- Test: `tests/test_user_management.py`

**Interfaces:**
- Consumes: `create_user(username: str, password_hash: str, role: str) -> int`
- Produces: `POST /admin/users`
- Produces: `POST /admin/users/{username}/disable`

- [ ] Write tests that admin can create business users.
- [ ] Write tests that normal users cannot create users.
- [ ] Add user form on admin page with username, password, and role.
- [ ] Support roles `admin` and `user`.
- [ ] Prevent disabling the last active admin account.
- [ ] Run `pytest tests/test_user_management.py -v`.
- [ ] Commit: `feat: add admin user management`.

### Task 7: Startup, Migration, And Compatibility

**Files:**
- Modify: `app/main.py`
- Modify: `app/core/config.py`
- Modify: `README.md`
- Modify: `Dockerfile` if database path or static/template files need copy handling.
- Test: `tests/test_startup_compatibility.py`

**Interfaces:**
- Consumes: `init_database() -> None`
- Consumes: admin bootstrap settings

- [ ] Write tests that app startup initializes the database.
- [ ] Write tests that legacy env-only `/otp` still works when `OTP_SECRET` is configured.
- [ ] Ensure Docker image copies templates and static files.
- [ ] Update README with setup, admin login, adding portal secrets, business dashboard, and API compatibility.
- [ ] Document that the UI countdown updates locally and backend refresh occurs at MFA rollover.
- [ ] Run full test suite: `pytest -v`.
- [ ] Commit: `docs: document multi-user otp portal`.

### Task 8: Local Verification

**Files:**
- No new code unless verification exposes a bug.

**Interfaces:**
- Verifies: complete portal behavior.

- [ ] Create a local `.env` using non-production test values.
- [ ] Start server: `uvicorn app.main:app --reload`.
- [ ] Open `/login` and sign in as admin.
- [ ] Add two test TOTP secrets.
- [ ] Create one business user.
- [ ] Sign out and sign in as business user.
- [ ] Confirm `/dashboard` shows multiple live OTP cards.
- [ ] Confirm countdown ticks locally and OTP code changes only when the MFA window changes.
- [ ] Confirm `/otp/{portal_name}` works with API key.
- [ ] Confirm unknown portal returns 404.
- [ ] Commit any verification fixes separately.

## Self-Review

- Spec coverage: admin login, user login, multi-secret registration, portal-specific OTP endpoints, Google Authenticator-style dashboard, and MFA-window refresh behavior are covered.
- Placeholder scan: no TBD or TODO placeholders remain.
- Type consistency: database, auth, TOTP, admin, and UI task interfaces use matching names across tasks.
