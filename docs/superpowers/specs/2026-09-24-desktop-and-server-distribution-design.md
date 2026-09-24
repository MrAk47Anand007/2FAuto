# 2FAuto Desktop and Server Distribution Design

## Intent

Let an administrator or business user install 2FAuto without Python, Bun, Docker, environment files, or command-line setup. Preserve the existing portal permissions, audited code reveals, scoped automation credentials, and encrypted TOTP seeds. A business user should be able to open a desktop window and see only the portals granted to them.

## Product roles

| Role shown in setup | Runs on the machine | Access from other machines | Startup |
| --- | --- | --- | --- |
| Server | API, persistent vault, and browser UI; no desktop window | Allowed only after an administrator configures HTTPS and the listening address | OS service at machine boot |
| Desktop + Web | Desktop window, local API, persistent vault, and browser UI | Off by default; an administrator can explicitly enable hosting | Local background process at user sign-in by default, with an opt-out setting |
| Desktop Client | Desktop window connecting to an existing 2FAuto server; no local vault | Connects outbound to a configured HTTPS server | Application at user sign-in if enabled |

Ship Server and Desktop + Web first. Desktop Client is a separate later milestone, because it needs a reliable connection setup and trust flow. The product may offer one Windows MSI with a mutually exclusive role choice. macOS and Linux get their own installers or packages with equivalent choices; MSI is Windows-specific. A Server installation does serve the web UI, although it has no desktop window. The Desktop + Web role can be used privately on one PC or as an explicitly configured small team host.

## Current state and target process layout

The repository currently runs FastAPI with SQLite, a TanStack Start React UI with a Node runtime, and a Caddy same-origin gateway in Compose. The React API client uses relative `/api` and `/admin` paths. FastAPI validates same-origin requests and browser sessions use cookies. The packaged product must preserve that same-origin behavior.

The target is one HTTP origin per installed vault: the FastAPI service serves the built React UI and API from the same host and port. The installer bundles the Python runtime and compiled UI assets. A short build validation milestone must prove the React UI can be produced as client-side assets without live TanStack server functions. Packaged mode must give `/login` and `/app/*` to React while keeping the original server-rendered pages available in the existing deployment path; FastAPI's current `/login` route cannot take precedence in packaged mode. If the static build proof fails, the fallback for the first release is a bundled Node UI process behind a packaged local gateway; the product behavior and role contract remain the same. Neither path may rely on a user's separately installed Python, Node, Bun, or Docker.

The Desktop + Web shell is a Tauri window that opens the local origin after the backend reports readiness. Its supervisor starts one backend instance, checks readiness, displays failures, and stops its own child when appropriate. Closing the window may leave the background process running only when the user explicitly enabled that setting. Server mode runs the packaged backend as an OS service and does not depend on an interactive login. The existing Docker path remains usable.

## First-run configuration and identity

The installer selects a role and installation location; it does not accept or log secrets. An initial setup flow creates a unique session-signing secret, a unique encryption key, and the first administrator account. Before this setup completes, the backend binds only to loopback and exposes only setup and health routes; no OTP or administration API can be used. Setup is single-use and cannot be replayed after an administrator exists. Unattended server configuration uses a protected input file or standard input, never password or key command-line arguments.

Persist data in OS application-data locations, outside the installation directory. Keep the encryption key separate from SQLite and protect it using the platform's secure storage or an OS-protected file with restricted access. The storage design must work under the actual service account on Windows, macOS, and Linux; a key protected for one interactive user must not silently be inaccessible to a machine service. The normal UI remains locked behind the existing login, session, grant, and step-up checks.

## Network and web behavior

Desktop + Web listens on loopback by default. Enabling remote access requires an explicit administrator action, a configured HTTPS endpoint, and a clear firewall/network prompt; no plain HTTP LAN hosting. Server mode may start loopback-only until its administrator completes the network setup. No wildcard CORS or broad origin exception is introduced. Once configured, browser and desktop requests reach the same origin as the API, preserving cookies and CSRF checks. Automation clients continue using the scoped bearer API over HTTPS.

Local API ports are selected or checked to avoid conflicts and a second running instance must attach to the existing healthy process or show an error instead of opening the SQLite database twice. The UI reports backend unavailable, setup incomplete, invalid TLS, wrong server address, and clock drift in actionable language. OTPs and secrets remain absent from logs, notifications, installer output, and crash reports.

## Data lifecycle

An upgrade preserves the vault, administrator accounts, grants, audit events, and key material. Schema changes use ordered migrations, take a recoverable pre-upgrade backup, and stop on failure without opening a half-migrated vault. Backups include both SQLite data and the required key material in an encrypted, passphrase-protected export; restore is exercised on a fresh installation. Uninstall preserves user data by default and offers an explicit separate purge flow. Migration from an existing Docker or `.env` installation is an explicit export/import operation, not automatic discovery of local secrets.

## Platform and release scope

1. Windows is the first supported installer: signed MSI, Server Windows service, and Desktop + Web app with optional sign-in autostart.
2. macOS follows with a signed/notarized app and package, a launch daemon for Server, and a login item for Desktop + Web.
3. Linux follows with `.deb` and `.rpm` packages, a systemd service for Server, and desktop autostart for Desktop + Web. AppImage may be offered for desktop use but is not the server installation path.

Each platform needs clean-install, upgrade, uninstall/reinstall, service restart, backup/restore, network, and sleep/wake checks on a real OS image. A CI build alone does not count as installer or runtime proof. Signed installers and update packages are published only after the role matrix passes. Automatic updates are a later milestone and must not restart a server during an active operation or risk an unbacked migration.

## Explicit exclusions for the first release

No cloud account, cross-device sync, automatic server discovery, mobile app, or multi-writer replication. One vault owns one SQLite database. Users connecting to a shared vault use the Server web UI in the first release; Desktop Client comes after the host roles are reliable.

## Success criteria

- A Windows administrator can install Server, complete setup, reboot without logging in, and reach the web UI over configured HTTPS.
- A Windows user can install Desktop + Web, complete setup without a terminal, restart/sign in, and reveal an authorized OTP in the desktop window and local browser.
- A fresh second device cannot reach Desktop + Web until hosting is explicitly enabled and HTTPS configured.
- Existing authorization, audit, CSRF, session expiry, and scoped automation behavior continue to pass tests and interactive checks.
- Backup and restore recover the same TOTP output from a fresh installation with the correct key; losing the key is clearly explained as unrecoverable.
- Installing, upgrading, or uninstalling never prints secrets, silently deletes a vault, or leaves an exposed unconfigured server.

## Reference documentation

- [Tauri external binaries](https://v2.tauri.app/develop/sidecar/) and [autostart](https://v2.tauri.app/plugin/autostart/)
- [TanStack Start SPA mode](https://tanstack.com/start/latest/docs/framework/react/guide/spa-mode)
- [Windows Installer service installation](https://learn.microsoft.com/en-us/windows/win32/msi/serviceinstall-table)
- [Tauri platform distribution](https://tauri.app/distribute/)
