# Install 2FAuto

2FAuto has two host roles. **Desktop + Web** runs a private vault on your computer and opens it in a desktop window. **Server** starts a vault when the machine boots and lets people sign in through a browser. Both roles include the web UI and API. A separate Desktop Client for connecting to an existing server is planned later.

These packages are development builds until the signing and clean-machine checks in the [distribution plan](superpowers/plans/2026-09-24-desktop-and-server-distribution.md) pass. Do not distribute the unsigned MSI or OS packages as a release.

## Windows

1. Open `2FAuto-0.1.0-x64-roles.msi` as an administrator.
2. In **Select Features**, keep exactly one of **Desktop + Web** or **Server**. Desktop + Web is selected initially. Click the icon next to the other role and choose **Entire feature will be unavailable**. The installer rejects a selection with both or neither role.
3. For Desktop + Web, open **2FAuto** from the Start menu. It starts a local vault, then opens setup. Choose an administrator name and strong password. You can also open `http://127.0.0.1:8765` in a browser while the desktop app is running. Its tray menu can reopen the window or show desktop settings.
4. For Server, the **2FAuto Server** Windows service starts automatically at machine boot. On that machine, open `http://127.0.0.1:8765/setup` and create the first administrator. The service is initially reachable only on that machine.

The installer never asks for an administrator password or vault key. Setup happens in the local application after installation. Desktop + Web starts when the user signs in by default; turn this off in **Desktop settings**. The separate **Keep the vault running when I close the window** choice defaults to off.

Windows Server data and keys are stored under `%ProgramData%\2FAuto`; Desktop + Web uses the signed-in user's local application-data folder under `com.twofauto.desktop`. Windows restricts the Server folder to LocalService, SYSTEM, and administrators. An ordinary uninstall leaves both vaults in place.

## Linux

Install the **Server** `.deb` or `.rpm` for a systemd service, or the Tauri **Desktop + Web** `.deb` or `.rpm` for an interactive desktop. The service starts at boot and initially listens on `127.0.0.1:8765`. Complete setup locally or through an SSH tunnel. Server data stays in `/var/lib/2fauto`; the package does not remove it on uninstall. The `twofauto` service account owns that directory.

Desktop + Web starts its own user-scoped backend and stores data in the user's local application-data directory. Its sign-in startup choice is in desktop settings.

## macOS

Install the **Server** `.pkg` for a launch daemon, or the **Desktop + Web** `.app`/`.dmg` for an interactive desktop. Server setup is available at `http://127.0.0.1:8765/setup` on the Mac. Server data stays in `/Library/Application Support/2FAuto` with owner-only access. The launch daemon currently runs under the system account; review this account choice and complete signed/notarized VM checks before release.

## Make a server available to other machines

Finish first-run administrator setup before enabling network access. Obtain a TLS certificate with a Subject Alternative Name matching the hostname people will use, and place its certificate and private key where the service account can read them. Stop the service, then run the installed runtime's `configure-https` command with its config path, `--bind` address, `--hostname`, `--cert` path, and `--key` path. Restart the service and open only the HTTPS port in the firewall. The runtime validates the certificate, matching hostname, and administrator state before it binds remotely. Do not use a plain HTTP reverse proxy or open port 8765 to the LAN while it is loopback-only.

For example, on Windows run PowerShell as administrator (replace the hostname and certificate paths):

```powershell
Stop-Service 2FAuto
& 'C:\Program Files\2FAuto\twofauto-runtime.exe' configure-https --config 'C:\ProgramData\2FAuto\runtime.json' --bind 0.0.0.0 --hostname vault.example.com --cert 'C:\ProgramData\2FAuto\tls\server.crt' --key 'C:\ProgramData\2FAuto\tls\server.key'
Start-Service 2FAuto
```

The TLS key file must have service-account-only read permission. Browser sessions use secure cookies on HTTPS; API requests still use the existing grant and bearer-token checks.

## Backup and restore

Use the installed runtime's `backup --config CONFIG --output ARCHIVE` command. It prompts for a recovery passphrase without putting it in the command line or logs. The archive contains a consistent SQLite snapshot and the required keys, encrypted together. Store the archive and passphrase separately. An unencrypted copy of the database alone cannot restore its OTP seeds.

To recover on a new installation, stop its service or desktop app, run `restore --config CONFIG --input ARCHIVE`, enter the passphrase, and restart. Restore accepts the empty database made at first launch and refuses to overwrite a populated vault. Importing a previous Compose deployment is a separate `import-legacy --database OLD_DB --env-file OLD_ENV --output ARCHIVE` operation; restore that archive on the new host. Back up the original deployment first.

For migration failure, leave the service stopped and run `rollback-migration --config CONFIG`. A protected same-machine snapshot is taken before an installed vault's schema is changed. The service refuses to start while a migration marker remains. The encrypted passphrase archive is the portable recovery method for a different machine.

The [operations runbook](OPERATIONS-RUNBOOK.md) has exact service and recovery commands. Losing both the key and the encrypted archive makes existing OTP seeds unrecoverable.
