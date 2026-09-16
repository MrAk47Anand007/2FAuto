# OTP Portal operations runbook

This runbook is for synthetic and controlled recovery exercises. Never put a
real MFA seed, OTP, API credential, session cookie, or encryption key in a
command line, log, ticket, or repository.

## Configuration

Set `APP_ENV=production`, `COOKIE_SECURE=true`, `LEGACY_API_ENABLED=false`, and
provide a 32-byte `SECRET_ENCRYPTION_KEY` through the approved secret provider.
The current implementation reads that key from the process environment for
local development; production KMS/workload-identity integration is still a
release gate.

Keep the database and encryption key under separate access controls. Do not
store the key beside SQLite backups. Use an approved encrypted backup tool for
the output of `scripts/backup_sqlite.py`.

## Migration rehearsal

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

## Isolated restore

Restore only into a new restricted path:

```text
python scripts/restore_sqlite.py recovery/otp-backup.db recovery/restored/otp.db
```

Provide the matching key through the approved recovery secret provider, run the
readiness check, and verify that the restored application can authenticate,
authorize a synthetic portal, and write audit events. Never overwrite the live
database as a first restore step.

## Incident actions

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
