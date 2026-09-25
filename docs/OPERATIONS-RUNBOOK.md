# 2FAuto operations runbook

## Existing Compose deployment

This section is for synthetic and controlled recovery exercises. Never put a
real MFA seed, OTP, API credential, session cookie, or encryption key in a
command line, log, ticket, or repository.

### Configuration

Set `APP_ENV=production`, `COOKIE_SECURE=true`, `LEGACY_API_ENABLED=false`, and
provide a 32-byte `SECRET_ENCRYPTION_KEY` through the approved secret provider.
The current implementation reads that key from the process environment for
local development; production KMS/workload-identity integration is still a
release gate.

Keep the database and encryption key under separate access controls. Do not
store the key beside SQLite backups. Use an approved encrypted backup tool for
the output of `scripts/backup_sqlite.py`.

### Migration rehearsal

1. Stop writes and make an isolated backup:

   ```text
   python scripts/backup_sqlite.py otp_service.db recovery/otp-before-migration.db
   ```

2. Start the application with a synthetic encryption key. Startup adds the
   encrypted columns and migrates legacy rows atomically. If encryption fails,
   startup must fail; do not enable a plaintext fallback.
3. Inspect only metadata and ciphertext fields. Verify fixed-timestamp OTP
   vectors in-process without printing seeds or codes.
4. Exercise grant denial, grant expiry, credential revocation, session logout,
   and audit delivery before resuming writes.

### Isolated restore

Restore only into a new restricted path:

```text
python scripts/restore_sqlite.py recovery/otp-backup.db recovery/restored/otp.db
```

Provide the matching key through the approved recovery secret provider, run the
readiness check, and verify that the restored application can authenticate,
authorize a synthetic portal, and write audit events. Never overwrite the live
database as a first restore step.

### Incident actions

- Stolen client credential: revoke its client immediately, issue a replacement,
  review audit events, and migrate the owner workflow.
- Suspected seed disclosure: revoke affected portal grants, replace the seed in
  the upstream MFA provider, rotate the encryption key according to the KMS
  procedure, and preserve audit evidence.
- Lost admin access: use the separately controlled recovery administrator path;
  do not edit SQLite rows manually on the live host.
- Key-provider outage: keep the service fail-closed. Do not restore plaintext
  data or place a key beside a database backup.
- Database failure: stop writes, preserve the failing file and logs, restore to
  an isolated destination, and reconcile changes before any cutover.

## Installed 2FAuto operations

## Paths and service names

| Platform | Server service | Server vault | Installed runtime |
| --- | --- | --- | --- |
| Windows | `2FAuto` | `%ProgramData%\2FAuto` | `C:\Program Files\2FAuto\twofauto-runtime.exe` |
| Linux | `twofauto.service` | `/var/lib/2fauto` | `/usr/lib/2fauto/twofauto-runtime` |
| macOS | `com.twofauto.server` launch daemon | `/Library/Application Support/2FAuto` | `/usr/local/lib/2fauto/twofauto-runtime` |

The vault contains `runtime.json`, `otp_service.db`, and `vault-keys.bin`. Never move only the database. On Linux and macOS, an owner-only wrapping key outside the Server vault protects `vault-keys.bin`; keep that key store through upgrades and uninstall. A portable encrypted recovery archive can re-protect the vault on another machine. Ordinary package removal does not delete these directories. A separate manual data purge should happen only after verified backups and deliberate owner approval.

## Health and setup

`GET http://127.0.0.1:8765/health` confirms the process is alive. `/ready` returns 503 until setup creates the first administrator. Before setup, all OTP and administration routes return 503 and only loopback clients can reach the setup flow. `/api/setup/status` is local-only.

For Windows, use `Get-Service 2FAuto`, `Start-Service 2FAuto`, and `Stop-Service 2FAuto`. On Linux use `systemctl status|start|stop twofauto.service`. On macOS use `launchctl print system/com.twofauto.server` and `launchctl bootout`/`bootstrap` for the installed plist.

## HTTPS network setup

Finish setup, stop the service, place a certificate and private key in the protected vault directory, then run `configure-https` as shown in [installation](INSTALLATION.md). The certificate must be valid now, match the exact public hostname or IP address in its SAN, and match the private key. The runtime refuses a non-loopback bind without HTTPS. Restart the service and test `/ready` through the intended HTTPS hostname before opening the firewall. Keep port 8765 closed to other machines until this works.

If a cert expires or becomes unreadable, the service refuses to start. Renew the files with the same names and restricted permissions, then restart. Do not disable TLS or use HTTP as a recovery shortcut.

## Encrypted recovery archive

Use `backup --config CONFIG --output ARCHIVE`; type the passphrase at the prompt. This works while the vault is serving requests because it uses SQLite's online backup API. Test each archive on a fresh installation before depending on it. To restore, stop the service, use `restore --config CONFIG --input ARCHIVE`, and restart. A wrong passphrase makes no database changes. Restore refuses existing records.

On Linux, run backup and restore as `twofauto` with access to its protected vault. On Windows, use an elevated console for Server and the same signed-in user for Desktop + Web, because desktop keys use user-scoped DPAPI. A Server backup archive can move to another machine because it contains key material encrypted by the recovery passphrase. Treat that passphrase as a high-value secret.

## Upgrade or interrupted migration

Before changing an existing packaged database, startup saves its SQLite snapshot and protected key under `pre-upgrade/` and writes `migration.pending`. Successful migration sets schema version 1 and clears the marker. If startup fails, leave the service stopped. Inspect logs for the failure, retain the entire vault directory, then run `rollback-migration --config CONFIG` to restore the saved same-machine snapshot. Create a passphrase archive after a successful restart. Do not delete `migration.pending` manually.

Windows MSI major upgrades remove old program files and install new ones; the vault remains under ProgramData or the user's local application-data directory. Linux package uninstall also keeps `/var/lib/2fauto`; macOS server package payload is separate from its application-data directory. Reinstall or role changes need actual OS validation before production use.

## Release checks still required

The build pipeline checks source, artifacts, and package metadata. Release approval additionally needs a clean Windows VM for each MSI role, repair/upgrade/uninstall/reinstall, service reboot without login, HTTPS login and scoped automation, desktop close/reopen and sleep/wake, and a fresh-machine restore. Repeat the role matrix on macOS and Linux. Windows and macOS packages require signing, and macOS needs notarization. These checks are not established by unit tests or an unsigned local build.
