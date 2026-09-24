# 2FAuto Desktop and Server Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver installable Server and Desktop + Web roles for 2FAuto, starting with a signed Windows MSI and extending the same product contract to macOS and Linux.

**Architecture:** Package the existing FastAPI vault and React UI behind one local origin. A role-aware launcher runs it as an OS service or as a supervised desktop background process; a Tauri window opens that origin for Desktop + Web. Set up secrets and the first administrator after installation, then make remote access an explicit HTTPS-only configuration.

**Tech Stack:** Python 3.11+/FastAPI/SQLite, TanStack Start/React, Tauri 2, WiX Toolset for Windows MSI/service integration, pytest, Bun frontend build, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-24-desktop-and-server-distribution-design.md`

## Global Constraints

- Server includes the web UI but no desktop window; Desktop + Web includes a local vault and window.
- Windows MSI is first; macOS and Linux require native packages, not the MSI.
- No separate Python, Node, Bun, or Docker installation is required on target machines.
- One origin serves browser UI and API; keep current session, CSRF, grant, audit, and client-token protections.
- An unconfigured installation stays loopback-only and cannot serve OTPs.
- Remote access is explicitly enabled only with HTTPS.
- No passwords, TOTP seeds, codes, session secrets, or encryption keys in MSI properties, command lines, logs, or crash reports.
- Data and keys survive upgrades and ordinary uninstall; purge is a separate deliberate action.
- Do not change the existing Compose deployment or Lovable-connected frontend history to deliver the installers.

## File and component map

| Area | Files to create or modify | Responsibility |
| --- | --- | --- |
| UI build | `Secure Access Hub/vite.config.ts`, `Secure Access Hub/package.json`, `Secure Access Hub/src/start.ts`, build scripts under `scripts/` | Produce and validate a desktop/server static UI artifact; keep Compose's Node build working |
| Single origin | `app/main.py`, new `app/routes/frontend.py`, tests under `tests/` | Serve built UI routes/assets and API together in packaged mode without swallowing API 404s |
| Setup/state | `app/core/config.py`, `app/core/database.py`, `app/main.py`, new `app/core/installation.py`, new `app/routes/setup.py` | First-run state, secure key loading, admin creation, setup lockout, data paths |
| Launcher | new `packaging/runtime/` | Start/check/stop one packaged backend with selected role and data directory |
| Desktop | new `desktop/` Tauri project | Window, tray/status, startup choice, backend readiness and error UX |
| Windows installer | new `packaging/windows/` WiX project | Role picker, service install, MSI lifecycle, signing inputs |
| Backups | `scripts/backup_sqlite.py`, `scripts/restore_sqlite.py`, new packaged backup commands | Encrypted vault export, restore, migration, and uninstall behavior |
| Release | `.github/workflows/`, `docs/OPERATIONS-RUNBOOK.md`, new `docs/INSTALLATION.md` | Build artifacts, cross-platform test evidence, operator guidance |

File names for new modules are assigned here so each task has a clear owner. Existing functions and route shapes should be reused where they already satisfy the contract.

## Review Focus

1. A second launch or occupied port must not create two writers to the same SQLite vault; Task 3 tests this.
2. A power loss during setup or migration must not leave an exposed half-configured vault; Tasks 2 and 7 test this.
3. A user installing Desktop + Web must not accidentally enable LAN access; Tasks 2 and 5 test this.
4. An upgrade or uninstall must not erase the database or encryption key; Tasks 6 and 7 test this.
5. Wrong clock or unavailable backend must produce actionable UI status without exposing codes; Tasks 4 and 5 test this.

---

### Task 1: Prove and build the single-origin UI

**Files:** Modify `Secure Access Hub/vite.config.ts`, `Secure Access Hub/package.json`, `app/main.py`; create `app/routes/frontend.py`, `scripts/build_packaged_ui.py`, and `tests/test_packaged_ui.py`.

**Deliverable:** A packaged build serves `/login`, `/app`, asset files, and existing `/api/*` endpoints from one origin. Compose retains its current Node UI path.

- [x] Add a build command for a static TanStack Start shell and inspect the output for live server-function calls. If the Lovable config cannot emit a safe static build, record the failing build and use a bundled Node UI plus local gateway for this task; do not silently drop routes or protections.
- [x] Add a packaged-mode frontend route after API routers; it must return the SPA shell for `/login` and `/app/*`, real assets for asset paths, and 404 for unknown `/api/*` paths. In packaged mode, do not register the legacy server-rendered `/login` route ahead of the React route; keep that route in existing deployment mode.
- [x] Add tests for login route, nested app route, asset MIME type, API 404, and an API mutation that still rejects missing CSRF.
- [x] Run `bun run build` in `Secure Access Hub/`, `python -m pytest tests/test_packaged_ui.py -q`, and `python -m pytest -q`.
- [x] Commit the isolated UI build and serving change.

### Task 2: Safe first-run installation state

**Files:** Modify `app/core/config.py`, `app/core/database.py`, `app/main.py`; create `app/core/installation.py`, `app/routes/setup.py`, and `tests/test_installation_setup.py`.

**Deliverable:** A packaged installation starts unconfigured on loopback, creates keys and the first administrator once, then starts the normal app.

- [ ] Introduce explicit `development`, `test`, `production`, and packaged-installation configuration paths without weakening production checks for Compose.
- [ ] Store vault data outside the executable directory and persist encryption/session keys in protected storage compatible with the selected OS account.
- [ ] Make setup completion atomic: generate keys, validate an administrator password, create the first admin, write a setup marker, then expose normal routes. Reject concurrent or repeated setup attempts.
- [ ] Test incomplete setup against OTP/admin routes, repeated setup, interrupted setup, sample keys/passwords, and default loopback binding.
- [ ] Run `python -m pytest tests/test_installation_setup.py -q` and the full backend suite.
- [ ] Commit the first-run foundation.

### Task 3: Packaged runtime and role contract

**Files:** Create `packaging/runtime/` entry point, process lock and health helpers, plus `tests/test_packaged_runtime.py`; modify `app/core/config.py` only where launch settings require it.

**Deliverable:** One self-contained backend executable accepts `server` or `desktop-web` role and reports readiness without printing secrets.

- [ ] Build a Python executable with bundled dependencies and UI assets; verify it runs on a clean Windows VM without Python or Node installed.
- [ ] Define a versioned role/config file in the OS data directory. Treat role, bind address, port, and data path as validated inputs; refuse unknown roles and unsafe remote HTTP settings.
- [ ] Add a single-instance lock scoped to the data directory and reject a second writer, including when a port is already occupied.
- [ ] Test launch, clean shutdown, crash/restart, occupied port, corrupt config, missing key, and an existing healthy instance. Check logs for accidental secret output.
- [ ] Run the runtime tests and a real packaged-executable smoke test; record executable size and cold-start time as release baselines.
- [ ] Commit the packaged runtime.

### Task 4: Desktop + Web shell

**Files:** Create `desktop/` Tauri app with Rust process supervision, frontend entry, status/error views, and desktop-specific tests.

**Deliverable:** The desktop installer opens the existing 2FAuto UI, starts its local backend, and optionally starts at sign-in.

- [ ] Bundle the packaged backend as a platform-specific Tauri sidecar and start it with a loopback-only configuration.
- [ ] Wait for `/ready` before opening the UI; show setup, restarting, port conflict, backend failure, and clock-drift states without exposing an OTP in notifications.
- [ ] Enable sign-in autostart by default for Desktop + Web, with a clear opt-out setting; add a separate setting for whether closing the window leaves the local process running.
- [ ] Add an end-to-end test for first launch, second launch, close/reopen, sign-out/sign-in, sleep/wake, and offline operation on Windows.
- [ ] Commit the desktop shell.

### Task 5: Network setup and server operation

**Files:** Create a packaged network configuration flow under `app/routes/setup.py` and runtime/service launch files in `packaging/runtime/`; modify `docs/OPERATIONS-RUNBOOK.md`; add tests under `tests/`.

**Deliverable:** A server runs without a logged-in user; remote browser and automation access work only over configured HTTPS.

- [ ] Keep both roles loopback-only until administrator setup completes. Add explicit HTTPS endpoint/certificate configuration and validate certificate, hostname, and same-origin request behavior before enabling remote bind.
- [ ] Preserve scoped bearer-client access and browser CSRF behavior through the packaged origin; add tests for valid origin, wrong origin, insecure remote request, and expired/revoked grant.
- [ ] Confirm the Windows service account can read the key and write its vault, logs, and backups with restricted permissions.
- [ ] Reboot a Windows VM without login, verify service readiness, browser login, OTP reveal, and scoped automation request.
- [ ] Commit the network/service behavior.

### Task 6: Windows MSI and upgrade lifecycle

**Files:** Create `packaging/windows/` WiX source and build scripts; add Windows jobs to `.github/workflows/`; create `docs/INSTALLATION.md`.

**Deliverable:** One Windows MSI offers mutually exclusive Server and Desktop + Web choices, installs their required components, and preserves vault data on upgrade/uninstall.

- [ ] Implement the role selector without asking for passwords, tokens, or encryption keys in MSI UI or properties.
- [ ] Install Server as an automatic Windows service; install Desktop + Web with Tauri app registration and optional user sign-in startup. Put mutable data outside Program Files.
- [ ] Test fresh install, repair, same-version reinstall, upgrade, role change, uninstall/reinstall, and failed upgrade; preserve data unless a separate explicit purge action runs.
- [ ] Sign MSI and bundled executables in the release workflow; verify signatures and installer logs on a clean VM.
- [ ] Document install steps, role selection, network setup, backup location, and troubleshooting with business-user language.
- [ ] Commit the installer and Windows release workflow.

### Task 7: Backup, restore, and migration

**Files:** Modify `scripts/backup_sqlite.py`, `scripts/restore_sqlite.py`; create packaged backup/restore entry points and `tests/test_packaged_backup.py`; update `docs/OPERATIONS-RUNBOOK.md`.

**Deliverable:** An administrator can recover a vault on a clean installation and import a supported existing deployment.

- [ ] Export SQLite and its matching key material into one encrypted archive protected by a user-supplied recovery passphrase; never put the passphrase in process arguments.
- [ ] Before any schema migration, create a recoverable backup and stop safely if backup or migration fails.
- [ ] Test wrong passphrase, missing key, interrupted export, fresh-machine restore, Docker `.env`/volume import, and TOTP equivalence after restore.
- [ ] Verify ordinary uninstall leaves vault data intact; test explicit purge separately.
- [ ] Commit recovery and migration support.

### Task 8: macOS and Linux packages

**Files:** Create `packaging/macos/`, `packaging/linux/`, platform CI jobs, and OS-specific sections of `docs/INSTALLATION.md`.

**Deliverable:** Equivalent role choices and data-safety behavior on macOS and Linux.

- [ ] Package Server as a macOS launch daemon and Linux systemd service; package Desktop + Web as a signed/notarized macOS app and `.deb`/`.rpm` desktop package with optional sign-in autostart.
- [ ] Validate service-account access to keys and data paths independently on each OS; do not reuse Windows key protection assumptions.
- [ ] Run the same install/upgrade/uninstall, HTTPS, backup/restore, reboot, and sleep/wake matrix on both platforms.
- [ ] Publish packages only after signatures and real-OS smoke tests pass; document per-platform limitations.
- [ ] Commit cross-platform packaging and release docs.

## Release gates

1. **Architecture gate:** Task 1 demonstrates a working static UI or records the bundled Node fallback before installer work relies on it.
2. **Windows development build:** Tasks 1–5 pass on a clean Windows VM; the manually installed package is used only for internal evaluation.
3. **Windows beta:** Tasks 6–7 pass, including reboot, HTTPS remote use, upgrade, and fresh-machine restore.
4. **Cross-platform release:** Task 8 passes on clean macOS and Linux images; installers are signed where the OS supports signing and documented where Linux distribution formats differ.

Backend unit tests, frontend build, and CI packaging are necessary evidence. They do not substitute for the actual installer, reboot, browser, desktop, and restore checks listed above.
