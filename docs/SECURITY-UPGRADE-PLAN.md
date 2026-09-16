# 2FAuto security and product upgrade plan

Date: 2026-09-16

Status: Code-verifiable Phases 1–7 implemented in this worktree; release remains blocked on external provider, deployment, recovery, and independent security evidence.

Baseline: main after README commit `2c52712`.

No plan guarantees an application is breach-proof. This plan defines a reviewable implementation, migration, and verification process for an application that holds reusable MFA seeds.

## 1. Outcome and scope

Deliver a shared OTP service where every person and automation client has explicit portal access, secrets are encrypted, credentials and sessions can be revoked, code retrieval is attributable, and backups can be restored safely.

Keep FastAPI and initially retain Jinja templates and lightweight JavaScript. Upgrade incrementally; a frontend rewrite and microservices are not prerequisites. Default scope is one organization with multiple teams, not a public multi-tenant SaaS. Public signup, cross-company tenancy, seed export, and mobile offline vaults are excluded from the first release.

Use synthetic MFA seeds throughout development, CI, screenshots, and browser testing. Never copy production seeds into fixtures, chat, logs, or issue attachments.

## 2. Observed baseline

| Area | Evidence in repository | Required change |
|---|---|---|
| Storage | `app/core/database.py`: plaintext `otp_entries.secret` | Authenticated encryption and separate key custody |
| Authorization | `app/routes/ui.py`: returns all active portals to any authenticated user | Explicit grants enforced on every retrieval |
| Automation | `app/middleware/auth.py`: shared API key; HMAC signs only timestamp | Scoped client identities; retire shared-key access |
| Sessions | `app/core/security.py`, `app/routes/auth.py`: signed 12-hour cookie; no Secure flag; logout deletes cookie only | Revocable server-side sessions and secure transport |
| Administration | `app/routes/admin.py`: no explicit CSRF protection; add/disable/delete lifecycle | CSRF, step-up, edit/archive/reactivate, atomic invariants |
| UI | `app/static/dashboard.js`: bulk retrieval, full rerender each second, weak failure handling | Reveal-based retrieval, stable countdowns, explicit stale state |
| Bootstrap | `app/main.py`: active-only username lookup before insert | One-time bootstrap independent of active status |
| Verification | Five existing tests in two test modules | Security, migration, browser, deployment, and recovery evidence |

The README's production-ready and replay-prevention claims must be corrected during Phase 0. A timestamp window limits replay duration but does not prevent reuse within that window. This baseline is a code review, not a penetration test or proof of deployed settings.

### Phase 0 evidence log

- 2026-09-16: confirmed the current SQLite schema stores `otp_entries.secret` in plaintext, the dashboard returns all active portals to any authenticated user, automation uses one global API key, and browser sessions are signed client-side cookies without server revocation or the `Secure` flag.
- 2026-09-16: corrected README/API description claims for production readiness, replay prevention, plaintext storage, and session security.
- 2026-09-16: changed admin bootstrap lookup to include inactive records so a disabled configured admin is not recreated on restart; covered by regression tests.
- 2026-09-16: added explicit environment/cookie settings, production rejection of sample credentials and insecure cookie configuration, security response headers, and `no-store` headers for OTP responses.
- 2026-09-16: added AES-GCM portal-secret storage with random nonces, portal/version-bound associated data, key-version metadata, and atomic startup migration of legacy plaintext rows; portal listings no longer select secret material.
- 2026-09-16: added opaque hashed server sessions, idle/absolute expiry, session listing/revocation, CSRF and same-origin protection, and SQLite-backed bounded login throttling.
- 2026-09-16: added five-minute password re-authentication step-up state for sensitive portal, grant, and client operations; independent MFA/SSO remains an external policy gate.
- 2026-09-16: added deny-by-default user grants with expiry/revocation, user-scoped dashboard retrieval, durable redacted audit events before OTP release, and an audit search endpoint.
- 2026-09-16: added teams, active memberships, and expiring team portal grants to the same authorization evaluator; direct user and team grants are both deny-by-default.
- 2026-09-16: added scoped automation clients, one-time opaque bearer credentials, client portal grants, credential/client revocation, and an explicit legacy global-key compatibility flag defaulting off.
- 2026-09-16: replaced bulk browser OTP loading with metadata-only portal listing and CSRF-protected explicit reveal; codes are held only in transient page memory and hidden at expiry.
- 2026-09-16: added readiness checks, response transport headers, container health signaling, SQLite backup/restore helpers, an initial CI workflow, and an operator recovery runbook.
- 2026-09-16: made the final-active-administrator check transactional, added admin-visible five-minute step-up re-authentication, added team management controls, and covered backup/restore plus final-admin behavior with tests.
- 2026-09-16: added individual automation-credential inventory/revocation for overlap rotation and strict local `otpauth://totp` provisioning-URI parsing; no supplied URL or QR content is fetched.
- 2026-09-16: completed a local Chromium smoke flow covering admin step-up, explicit grant/reveal, expiry hiding, empty browser storage, logout, and post-logout denial; this is not deployed-edge or device evidence.
- 2026-09-16: added CI dependency vulnerability auditing alongside secret scanning and changed the container healthcheck to use readiness.
- Remaining Phase 0/1 work: assign owners for legacy consumers and recovery, record the permission matrix and unresolved provider decisions, and complete versioned schema migrations and constraints.
- Remaining Phase 2 work: connect production key custody to the selected KMS/secret manager and rehearse protected backup/restore and interrupted migration handling; resumable rotation is implemented as `scripts/rotate_secrets.py` but still needs an operational rehearsal.
- Remaining Phase 3–8 work: independent MFA/SSO and recovery policy, team/approval workflows, request-signing/nonce policy if required, PostgreSQL and multi-instance deployment proof, encrypted backup rehearsal, browser/device/A360 acceptance, external dependency review, and independent security review.

### Baseline inventory

| Concern | Current evidence | Phase 0 implication |
|---|---|---|
| Interactive users and portal data | SQLite tables are created directly by `app/core/database.py`; there are no versioned migrations. Existing records cannot be assumed to be synthetic. | Owner must inventory users/portals in-process without exporting secrets before migration design is finalized. |
| Automation consumers | Legacy API routes remain documented as time-boxed compatibility paths; `totp_a360.py` now accepts a portal name and scoped client token rather than a seed. | Assign an owner to each legacy consumer and migrate it to a scoped client before retiring the global key. |
| Deployment | `Dockerfile` runs as non-root and now has a readiness healthcheck plus CI, but the repository still has no reverse-proxy/TLS profile, shared-database deployment profile, or resource limits. | Deployed-edge and multi-instance claims remain unverified; Phase 7 deployment work is still required. |
| Recovery | SQLite backup/restore helpers and an operator runbook are present, but they do not encrypt backups or prove isolated restore, key recovery, migration interruption, RPO, or RTO. | Recovery owner, key custody, and rehearsal evidence remain unresolved decisions. |
| Test evidence | The suite covers authentication, authorization, encrypted storage, scoped clients, portal behavior, and backup/restore helpers; a local Chromium smoke flow covers the main browser reveal lifecycle. No deployed-edge, A360 Control Room, migration rehearsal, encrypted-backup, or independent-review proof exists. | Treat current results as source/unit/local-browser evidence only, not production-readiness or compatibility evidence. |

## 3. Threat model and non-negotiable rules

Protect MFA seeds, current OTPs, account passwords, API credentials, sessions, encryption keys, backups, and audit integrity. Consider database theft, compromised ordinary users, malicious administrators, stolen browser sessions, compromised bots, login abuse, CSRF/XSS, replay, dependency compromise, and host compromise.

Trust boundaries: browser to reverse proxy; proxy to application; bot to API; application to database; application to key provider; application to audit destination; backup operator to recovery environment.

- Deny access unless an active identity has an explicit active grant. UI hiding is not authorization.
- Administration does not implicitly grant code retrieval. Separate metadata management, grants, retrieval, and audit permissions.
- A platform administrator able to grant themselves access remains privileged; separation of duties and approval policy must address that risk.
- Encrypt seeds using a maintained cryptography library and authenticated encryption. Do not invent cryptography or store encryption keys beside database backups.
- Encryption at rest protects database theft; it does not prevent a compromised running application with decrypt permission from accessing seeds.
- Never log seeds, OTPs, passwords, cookies, authorization headers, provisioning URIs, or QR contents. Include error reporting and proxy logs in this rule.
- Every successful code release must have a durable audit event. If authorization, decryption, or mandatory auditing fails, do not return a code.
- Never cache sensitive responses at browsers, proxies, service workers, or CDNs. Do not persist codes or seeds in browser storage.
- Access revocation blocks future retrieval; it cannot retract an OTP already delivered and still valid at its provider.
- The vault's own authentication factor must be independent of the seeds stored inside the vault.

## 4. Architecture and data contracts

### Proposed modules

- `app/core/config.py`: typed settings, deployment profiles, secure startup validation.
- `app/db/` and `migrations/`: schema, repositories, transactional migrations.
- `app/services/authorization.py`: one policy evaluator shared by HTML and API routes.
- `app/services/secrets.py`: encryption/decryption and key-version lifecycle.
- `app/services/otp.py`: authorized, audited OTP issuance orchestration.
- `app/services/sessions.py`: session creation, expiry, revocation, step-up state.
- `app/services/audit.py`: durable event creation and external delivery.
- `app/routes/`: HTTP validation and orchestration only; no duplicate policy logic.
- `tests/unit/`, `tests/integration/`, `tests/security/`, `tests/browser/`: evidence by layer.

These are intended boundaries, not a requirement to move every existing file in one commit.

### Logical entities

| Entity | Essential fields/invariants |
|---|---|
| Users | Immutable ID, unique identity, status, identity provider reference, credential/session version |
| Teams and memberships | Active membership; removal immediately removes derived access |
| Portals | Immutable ID, unique slug, issuer/account labels, environment, owner, status, period/digits/algorithm |
| Secret versions | Portal ID, ciphertext, nonce, wrapped data key if used, key version, encryption version, lifecycle state |
| Grants | Principal type/ID, portal ID, permission, expiry, grantor, approval reference |
| Sessions | Hashed opaque token, user ID, created/last-active/expiry timestamps, revoked state, step-up time |
| Automation clients | Owner, status, environment, permitted operations; no interactive privileges |
| API credentials | Lookup ID, verifier hash, expiry/revocation, client ID, last-use metadata |
| Audit events/outbox | Event ID, actor, target, action, result, reason category, timestamp, correlation ID |

Use PostgreSQL for the shared production target; SQLite can remain a development option only if both backends are tested. Use versioned migrations. Keep foreign keys and uniqueness constraints active; enforce last-admin and grant transitions transactionally. Prefer disabling/archive over irreversible deletion until retention policy is agreed.

### Proposed endpoints

- `GET /api/v1/portals`: only authorized metadata; no codes or seeds.
- `POST /api/v1/portals/{portal_name}/otp`: authorize, rate-limit, audit, and issue one code; browser calls require CSRF protection.
- `GET /api/v1/me/sessions`, `DELETE /api/v1/me/sessions/{id}`: list/revoke owned sessions.
- Administrative resources for users, teams, grants, portals, and automation clients: validate permissions separately for each action.
- Health endpoint exposes minimal liveness. Readiness checks dependencies without disclosing secrets or infrastructure details.

OTP response: `otp` as a string preserving leading zeroes, `issued_at`, `expires_at`, `server_time`, `period`, `portal_id`, and `request_id`. Use consistent error envelopes with safe machine-readable codes. Apply `Cache-Control: no-store` to both success and failure responses containing sensitive context.

For minimum-validity requests, bound requested validity below the portal period, bound server wait time, support cancellation, recheck access immediately before release, and avoid occupying unlimited workers. Return a clear retry response if the wait budget is exhausted.

## 5. Implementation phases and exit gates

Phases 0–5 establish the security foundation. Phase 6 depends on the Phase 3–5 contracts. Operational work can start earlier, but broad production rollout waits for Phase 8.

### Phase 0 — Baseline, inventory, and design decisions

- Inventory existing users, portals, automation consumers, deployment topology, and recovery expectations without exporting seeds.
- Record threat model, permission matrix, data flow, legacy endpoint usage, and risk register.
- Correct README security claims and document actual error/session behavior.
- Record decisions for identity provider, hosting, key custody, PostgreSQL, audit retention, and recovery ownership.
- Establish a reproducible synthetic development environment and baseline tests.

Exit: baseline evidence captured; every legacy consumer has an owner; acceptance criteria and unresolved decisions are recorded. No claim of production readiness.

### Phase 1 — Safe configuration and schema foundation

- Introduce environment profiles; production refuses sample credentials, missing key provider, insecure cookie settings, and incomplete required services.
- Replace unconditional recurring admin bootstrap with a deliberate one-time operation; disabled existing accounts must not trigger reinsertion.
- Add schema migrations, immutable IDs, lifecycle fields, transactions, and database constraints.
- Separate runtime/test dependencies and establish CI checks and dependency/secret scanning.
- Add secure headers and sensitive-response no-store policy; trust forwarded headers only from configured proxies.

Exit: clean install and upgrade fixtures pass; disabled-admin restart succeeds; production fails safely on invalid configuration; concurrent admin changes cannot remove the final recovery-capable administrator.

### Phase 2 — Encrypted secret storage and migration

- Implement an encryption abstraction backed by the selected KMS/secret manager; use unique nonces and authenticated associated data binding ciphertext to portal ID and schema/encryption version.
- Prefer envelope encryption with versioned wrapping keys. Local development may use a separately supplied development key; never silently fall back in production.
- Restrict decryption to the OTP service path. Metadata listings must not load decrypted seeds.
- Add resumable migration tooling, validation counts, key availability checks, and interruption recovery.
- Implement key rotation with resumable progress and old-key retention until all live data and retained backups are accounted for.

Exit: ciphertext tampering and cross-portal substitution fail; missing keys never produce plaintext fallback; migrated synthetic seeds generate identical OTPs at fixed timestamps; raw database inspection finds no seed values in the new store.

### Phase 3 — Authentication, sessions, and request protection

- Implement server-side opaque sessions, storing token verifiers rather than raw tokens. Rotate sessions on login and privilege changes.
- Add Secure/HttpOnly/SameSite cookies, CSRF tokens and origin checks, POST logout, idle/absolute timeout, and revoke-all behavior.
- Add account/IP-aware login throttling with shared state for multiple instances; bounded backoff must avoid easy permanent account denial of service.
- Select and implement either company SSO with enforced MFA or local passkeys/MFA plus a controlled recovery path before broad release.
- Add step-up authentication for grants, credential issuance, secret replacement, and critical administration.
- If local passwords remain, use maintained password hashing, safe length handling, generic errors, and protected reset flows.

Suggested initial policy for review: 15-minute human idle timeout, 8-hour absolute timeout, 5-minute freshness for sensitive step-up. These are tunable policy defaults, not universal standards. Automated dashboard refresh must not keep sessions active indefinitely.

Exit: stolen old cookies fail after logout/revocation; disabled users lose access immediately; missing/invalid CSRF is rejected; timeout and throttling work across instances; independent MFA and recovery are demonstrated.

### Phase 4 — Authorization and durable auditing

- Implement grants for people, teams, and clients with expiry and deny-by-default behavior.
- Enforce permission checks for list/detail/retrieve/change routes, including all legacy routes. Do not rely on client-supplied role or ownership.
- Separate portal administration from OTP reading; implement two-person approval where selected by policy.
- Record retrieval, denial, login, grant, credential, lifecycle, recovery, and key-rotation events with redaction.
- Commit audit events durably before releasing a code; an outbox may forward events to restricted external storage. Define backlog limits and failure behavior.

Exit: authorization matrix tests cover cross-user/team/client access, expired grants, revoked membership, and guessed IDs; unauthorized listing leaks no portal metadata; audit outage handling is verified. Events describe code issuance, not proof that a human viewed or used the code.

### Phase 5 — Automation API and legacy migration

- Issue one scoped identity per bot/integration with owner, expiration, revocation, and least-privilege grants.
- Prefer high-entropy opaque API tokens stored as verifier hashes for the first version; show credentials once and support overlap during rotation.
- If request signing is required, use a separate signing design/key: canonical method/path/body hash/timestamp/nonce and shared atomic nonce rejection. A hashed bearer token is not a recoverable HMAC key.
- Implement versioned API, bounded minimum-validity retrieval, documented errors, timeout/retry guidance, and client-specific rate limits.
- Update A360/Python examples to call the API without passing seeds in process arguments or logging returned codes.
- Migrate each legacy consumer to explicit portal grants. Time-box and monitor any compatibility mode; disable global-key routes before general release.

Exit: revoked/expired credentials fail immediately; client A cannot read client B's portals; rollover and timeout contracts pass; a real A360 workflow succeeds using synthetic secrets. No default fallback to the old global API key.

### Phase 6 — Dashboard and administration experience

- Build My Portals with search, favorites, issuer/account/environment labels, and team filters over authorized metadata.
- Fetch only explicitly revealed portal codes; auto-hide on timeout, logout, or inactivity. Clear sensitive UI state on session failure.
- Update countdown nodes in place; account for server/client clock offset using monotonic elapsed time after a response.
- Hide stale codes and disable copying on expiry, offline state, or refresh failure. Revalidate after tab resume and prevent overlapping/out-of-order refreshes.
- Add accessible keyboard/focus behavior, mobile layouts, clear loading/empty/error states, and non-color-only expiry indicators.
- Add admin pages for portal edit/archive/reactivate, people/teams, grants, clients, sessions, and audit search. Portal/team controls are present; client, session, and audit views remain API-only.
- Add provisioning URI/QR import with strict local parsing and validation; URI parsing is implemented locally, while QR decoding remains pending. Never upload provisioning content to third-party QR services or fetch arbitrary supplied URLs.
- Validate a replacement secret before activation. Provider-side MFA re-enrollment remains a separate required action.

Exit: browser tests cover failed requests, clock skew, sleep/resume, session expiry, no portals, large lists, keyboard use, and mobile layout; sensitive data is absent from local/session storage; screenshots use synthetic codes only.

### Phase 7 — Operations and recovery

- Provide production deployment configuration with TLS termination, persistent storage, restricted network exposure, resource limits, and non-root execution.
- Configure readiness, clock-drift monitoring, error/rate-limit metrics, audit delivery monitoring, and redacted alerts.
- Encrypt backups; separate data/key access; document restore commands, dependency recovery, and key-loss consequences.
- Write runbooks for lost admin access, stolen API credential, suspected seed disclosure, key-provider outage, and database failure.
- Define recovery point/time objectives with the owner; measure them in a synthetic recovery rehearsal.
- Scan application and container dependencies and review actionable findings; do not assume pinned versions are safe.

Exit: restore into an isolated environment succeeds and meets agreed objectives; key outage fails closed; resource and concurrency checks meet the agreed workload; operators can execute incident runbooks.

### Phase 8 — Pilot, security review, and release

- Run automated gates, browser/A360 acceptance, migration rehearsal, and independent security review appropriate to deployment exposure.
- Pilot with explicitly selected low-impact portals and users; observe access failures, usability, latency, and audit completeness.
- Resolve critical/high findings or block launch; document residual risks and accountable ownership.
- Cut over consumer by consumer, revoke legacy credentials, and confirm no remaining legacy traffic.
- Publish operator/user documentation and verified release notes; record rollback and incident contacts.

Exit: all mandatory gates below have evidence, owners sign off operational policy, and no plaintext-storage or global-key compatibility path remains enabled.

## 6. Migration and rollback procedure

1. Inventory consumers and schema version; validate target keys and recovery access.
2. Create a protected backup and prove it can be restored in isolation before touching live data.
3. Pause writes for the initial migration; use a maintenance window unless an independently tested online migration is implemented.
4. Copy into the new schema/store, encrypting seeds and retaining immutable source-to-target mappings. Assign approved grants explicitly; do not silently grant all users all portals.
5. Compare row counts, lifecycle state, and deterministic synthetic OTP tests. For real secrets, perform checks in-process without printing seeds or codes.
6. Cut over to the new application; invalidate old browser sessions and migrate clients according to their agreed schedule.
7. Verify authorization, OTP retrieval, audit delivery, and operator access; resume writes after acceptance.
8. Restrict and retire plaintext originals and backups according to the agreed retention procedure. SQLite pages/WAL, filesystem snapshots, and SSD behavior mean dropping a column is not proof of secure erasure.

Before writes resume, rollback can restore the pre-cutover snapshot in a restricted environment. After new writes, do not blindly restore an old snapshot: reconcile changes or forward-fix. Never roll back encryption by enabling a plaintext fallback. Never retire old keys while retained backups still need them. Rehearse interrupted migrations and rollback; do not delete any live data as part of merely preparing this plan.

## 7. Verification matrix

| Layer | Required proof |
|---|---|
| Unit | Encryption authentication, OTP fixed-time vectors/boundaries, policy decisions, expiry calculations |
| Integration | Database migrations, transactional invariants, sessions, audit durability, grant/client revocation |
| Security | ID enumeration/access bypass, CSRF, login abuse, cookie reuse, signing replay if enabled, XSS input handling, secret redaction |
| Browser | Reveal/copy/expiry, offline handling, focus, resume, mobile, session invalidation |
| Automation | A360 retrieval, leading zeroes, minimum validity, retries, denied/expired credentials |
| Operations | TLS/cookies/headers at deployed edge, multi-instance limits, clock drift, key/audit outage, backup restore |

Security tests must use both allow and deny cases and assert no code/seed leaks on errors. Do not measure readiness solely by test count or coverage percentage. CI and screenshots do not establish real deployment or A360 compatibility.

## 8. Implementation guidelines

- Work in small reviewable branches/PRs organized by phase. Preserve unrelated changes. No production secrets in development worktrees.
- For each change: record behavior, threat addressed, schema/API impact, tests, deployment steps, and rollback limits.
- Keep SQL parameterized, enforce server-side limits, and normalize identifiers consistently. Reject reserved slugs such as legacy route collisions where applicable.
- Avoid broad exception handling that turns authorization/decryption failures into empty successful responses.
- Use one centralized authorization path and one audited code-release path; routes must not decrypt or generate codes independently.
- Use real database integration tests for transaction/concurrency behavior; mocking does not prove locking or constraints.
- Recheck identity/grant status after bounded waits and before issuing a code. Avoid long-lived authorization caches without tested invalidation.
- Disable seed export initially. Metadata exports and audit exports also require authorization and retention controls.
- Do not introduce analytics/session recording on secret-bearing pages.
- Keep app logs and user-facing errors free of sensitive request bodies; test validation errors and traceback reporting as well as success paths.
- Treat API/UI compatibility as explicit, versioned contracts. Never preserve a security bypass merely for backward compatibility.
- Dependency upgrades require compatibility tests and vulnerability review; choose supported versions at implementation time.
- Every phase updates this plan's evidence/status and operator documentation. Code completion, automated verification, browser verification, and deployed verification are separate statuses.

## 9. Decisions to settle before affected phases

| Decision | Proposed starting position | Needed before |
|---|---|---|
| Hosting/exposure | One organization behind restricted access and HTTPS | Phase 1 deployment config |
| Identity provider | Existing corporate IdP with MFA if available; otherwise independent local MFA/passkeys | Phase 3 |
| Key custody | Managed KMS/secret manager using workload identity | Phase 2 production setup |
| Database | PostgreSQL for shared production | Phase 1 migrations |
| Privileged access | Admin does not automatically read OTPs; sensitive self-grants require separate approval | Phase 4 |
| Audit retention | Owner defines retention, access, and deletion policy; no indefinite default | Phase 4 operations |
| Bot credential lifetime | Expiring credentials with overlap rotation; owner agrees maximum lifetime | Phase 5 |
| Recovery objectives | Owner defines acceptable data loss and downtime | Phase 7 |
| Expected workload | Measure users, active reveals, bots, and peak calls before sizing | Phase 7 |

Do not invent cloud accounts, IdP tenant details, or recovery commitments. Unresolved provider choices do not block synthetic tests and interface work, but block the dependent production setup.

## 10. Release checklist

- [~] Seeds encrypted; key custody separate, tamper tests, and synthetic migration verified. Production KMS and rehearsal remain open.
- [x] People, teams, and bots restricted by explicit grants across implemented endpoints.
- [ ] Independent MFA/SSO and protected recovery demonstrated.
- [~] Secure sessions, CSRF, expiry, and revocation verified in source and local browser tests; deployed-edge proof remains open.
- [~] Scoped automation credentials and individual revocation implemented; legacy global-key paths remain only as explicit compatibility mode.
- [~] Durable redacted auditing implemented; external delivery and outage rehearsal remain open.
- [x] Dashboard cannot present expired codes as usable in the local browser flow.
- [~] Local synthetic browser flow verified; real A360/Control Room workflow remains open.
- [~] CI dependency and secret scanning configured; independent security review and finding disposition remain open.
- [ ] Backup restoration with key recovery and interrupted migration rehearsed in an isolated environment.
- [~] Runbook and redacted operational steps exist; owners, alerts, RPO/RTO, and residual-risk signoff remain open.
- [~] README and Markdown user guide state current capabilities; the open DOCX guide still needs synchronization after its file lock is released.

## 11. References

Use OWASP ASVS as a requirements catalog, select applicable controls, and attach evidence rather than claiming certification. Use storage/session guidance to review encryption custody and session lifecycle designs.

- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP MFA Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
