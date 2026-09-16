import json
import sqlite3
import time
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.secrets import encrypt_secret

ENCRYPTED_SECRET_PLACEHOLDER = "[encrypted]"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def get_db() -> sqlite3.Connection:
    db_path = Path(settings.DATABASE_PATH)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.DATABASE_PATH, factory=ClosingConnection)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS otp_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                secret TEXT,
                secret_ciphertext TEXT,
                secret_nonce TEXT,
                encryption_version INTEGER,
                key_version TEXT,
                period INTEGER NOT NULL DEFAULT 30,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                last_active_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                step_up_at INTEGER,
                revoked_at INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS login_throttle (
                key_hash TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                blocked_until INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS client_rate_limits (
                client_id INTEGER PRIMARY KEY,
                window_started_at INTEGER NOT NULL,
                request_count INTEGER NOT NULL,
                FOREIGN KEY(client_id) REFERENCES automation_clients(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS portal_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission TEXT NOT NULL CHECK(permission IN ('read', 'manage')),
                granted_by INTEGER NOT NULL,
                expires_at INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                UNIQUE(portal_id, user_id, permission),
                FOREIGN KEY(portal_id) REFERENCES otp_entries(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(granted_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                actor_user_id INTEGER,
                actor_kind TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                result TEXT NOT NULL,
                reason TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                FOREIGN KEY(actor_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS automation_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                owner_user_id INTEGER NOT NULL,
                environment TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'revoked')) DEFAULT 'active',
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                FOREIGN KEY(owner_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS api_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                lookup_id TEXT NOT NULL UNIQUE,
                verifier_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                revoked_at INTEGER,
                last_used_at INTEGER,
                FOREIGN KEY(client_id) REFERENCES automation_clients(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS client_portal_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                portal_id INTEGER NOT NULL,
                permission TEXT NOT NULL CHECK(permission IN ('read')),
                granted_by INTEGER NOT NULL,
                expires_at INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                UNIQUE(client_id, portal_id, permission),
                FOREIGN KEY(client_id) REFERENCES automation_clients(id) ON DELETE CASCADE,
                FOREIGN KEY(portal_id) REFERENCES otp_entries(id) ON DELETE CASCADE,
                FOREIGN KEY(granted_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_by INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS team_memberships (
                team_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                PRIMARY KEY(team_id, user_id),
                FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS team_portal_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                portal_id INTEGER NOT NULL,
                permission TEXT NOT NULL CHECK(permission IN ('read')),
                granted_by INTEGER NOT NULL,
                expires_at INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                UNIQUE(team_id, portal_id, permission),
                FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY(portal_id) REFERENCES otp_entries(id) ON DELETE CASCADE,
                FOREIGN KEY(granted_by) REFERENCES users(id)
            );
            """
        )
        _ensure_secret_columns(db)
        _ensure_session_columns(db)
        _migrate_plaintext_secrets(db)


def _ensure_secret_columns(db: sqlite3.Connection) -> None:
    """Add encrypted-secret columns to databases created by the old schema."""
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(otp_entries)")
    }
    additions = {
        "secret_ciphertext": "TEXT",
        "secret_nonce": "TEXT",
        "encryption_version": "INTEGER",
        "key_version": "TEXT",
    }
    for name, column_type in additions.items():
        if name not in existing_columns:
            db.execute(
                f"ALTER TABLE otp_entries ADD COLUMN {name} {column_type}"
            )


def _ensure_session_columns(db: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(sessions)")
    }
    if "step_up_at" not in existing_columns:
        db.execute("ALTER TABLE sessions ADD COLUMN step_up_at INTEGER")


def _migrate_plaintext_secrets(db: sqlite3.Connection) -> None:
    """Encrypt legacy rows atomically; fail startup rather than keep plaintext."""
    rows = db.execute(
        """
        SELECT id, portal_name, secret
        FROM otp_entries
        WHERE secret_ciphertext IS NULL
          AND secret IS NOT NULL
          AND secret != ?
        """,
        (ENCRYPTED_SECRET_PLACEHOLDER,),
    ).fetchall()
    for row in rows:
        encrypted = encrypt_secret(row["secret"], row["portal_name"])
        db.execute(
            """
            UPDATE otp_entries
            SET secret = ?,
                secret_ciphertext = ?,
                secret_nonce = ?,
                encryption_version = ?,
                key_version = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                ENCRYPTED_SECRET_PLACEHOLDER,
                encrypted["ciphertext"],
                encrypted["nonce"],
                encrypted["encryption_version"],
                encrypted["key_version"],
                int(time.time()),
                row["id"],
            ),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def create_user(username: str, password_hash: str, role: str = "user") -> int:
    now = int(time.time())
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (username.strip(), password_hash, role, now),
        )
        return int(cursor.lastrowid)


def get_user_by_username(
    username: str,
    *,
    include_inactive: bool = False,
) -> dict | None:
    with get_db() as db:
        query = "SELECT * FROM users WHERE username = ?"
        parameters: tuple[object, ...] = (username.strip(),)
        if not include_inactive:
            query += " AND is_active = 1"
        row = db.execute(query, parameters).fetchone()
    return row_to_dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


def create_session_record(
    token_hash: str,
    user_id: int,
    created_at: int,
    expires_at: int,
) -> int:
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO sessions
                (token_hash, user_id, created_at, last_active_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token_hash, user_id, created_at, created_at, expires_at),
        )
        return int(cursor.lastrowid)


def get_active_session(token_hash: str, now: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT
                s.id AS session_id, s.user_id, s.created_at,
                s.last_active_at, s.expires_at, s.step_up_at, s.revoked_at,
                u.username, u.role, u.is_active
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
              AND s.last_active_at > ?
              AND u.is_active = 1
            """,
            (token_hash, now, now - settings.SESSION_IDLE_TIMEOUT_SECONDS),
        ).fetchone()
    return row_to_dict(row)


def touch_session(session_id: int, now: int) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE sessions SET last_active_at = ? WHERE id = ? AND revoked_at IS NULL",
            (now, session_id),
        )


def mark_session_step_up(session_id: int, now: int) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE sessions SET step_up_at = ? WHERE id = ? AND revoked_at IS NULL",
            (now, session_id),
        )


def revoke_session(session_id: int, user_id: int | None = None) -> bool:
    with get_db() as db:
        if user_id is None:
            cursor = db.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (int(time.time()), session_id),
            )
        else:
            cursor = db.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE id = ? AND user_id = ? AND revoked_at IS NULL
                """,
                (int(time.time()), session_id, user_id),
            )
    return cursor.rowcount > 0


def revoke_all_sessions(user_id: int, except_session_id: int | None = None) -> None:
    with get_db() as db:
        if except_session_id is None:
            db.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (int(time.time()), user_id),
            )
        else:
            db.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE user_id = ? AND id != ? AND revoked_at IS NULL
                """,
                (int(time.time()), user_id, except_session_id),
            )


def list_user_sessions(user_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, created_at, last_active_at, expires_at, revoked_at
            FROM sessions
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _throttle_key_hash(key_hash: str) -> str:
    return key_hash


def is_login_throttled(key_hash: str, now: int) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT blocked_until FROM login_throttle WHERE key_hash = ?",
            (_throttle_key_hash(key_hash),),
        ).fetchone()
    return row is not None and int(row["blocked_until"]) > now


def record_login_failure(key_hash: str, now: int) -> None:
    with get_db() as db:
        row = db.execute(
            "SELECT failure_count FROM login_throttle WHERE key_hash = ?",
            (_throttle_key_hash(key_hash),),
        ).fetchone()
        failures = int(row["failure_count"]) + 1 if row else 1
        blocked_until = 0
        if failures >= 5:
            blocked_until = now + min(300, 30 * (2 ** min(failures - 5, 3)))
        db.execute(
            """
            INSERT INTO login_throttle (key_hash, failure_count, blocked_until, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key_hash) DO UPDATE SET
                failure_count = excluded.failure_count,
                blocked_until = excluded.blocked_until,
                updated_at = excluded.updated_at
            """,
            (_throttle_key_hash(key_hash), failures, blocked_until, now),
        )


def clear_login_throttle(key_hash: str) -> None:
    with get_db() as db:
        db.execute(
            "DELETE FROM login_throttle WHERE key_hash = ?",
            (_throttle_key_hash(key_hash),),
        )


def record_audit_event(
    *,
    actor_user_id: int | None,
    actor_kind: str,
    action: str,
    target_type: str,
    target_id: str | None,
    result: str,
    reason: str | None = None,
    metadata: dict[str, str | int | bool] | None = None,
    correlation_id: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            """
            INSERT INTO audit_events
                (
                    event_id, actor_user_id, actor_kind, action, target_type,
                    target_id, result, reason, metadata_json, created_at,
                    correlation_id
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                actor_user_id,
                actor_kind,
                action,
                target_type,
                target_id,
                result,
                reason,
                json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
                int(time.time()),
                correlation_id or str(uuid.uuid4()),
            ),
        )
    return event_id


def list_audit_events(limit: int = 100) -> list[dict]:
    bounded_limit = max(1, min(limit, 500))
    with get_db() as db:
        rows = db.execute(
            """
            SELECT event_id, actor_user_id, actor_kind, action, target_type,
                   target_id, result, reason, metadata_json, created_at,
                   correlation_id
            FROM audit_events
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_users() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, username, role, is_active, created_at FROM users ORDER BY username"
        ).fetchall()
    return [dict(row) for row in rows]


def active_admin_count() -> int:
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1"
        ).fetchone()
    return int(row["count"])


def disable_user(username: str) -> bool:
    with get_db() as db:
        # Serialize the final-admin check with the update. A separate count
        # followed by an update can allow two concurrent requests to disable
        # the last two active administrators.
        db.execute("BEGIN IMMEDIATE")
        user = db.execute(
            "SELECT id, role FROM users WHERE username = ? AND is_active = 1",
            (username.strip(),),
        ).fetchone()
        if user is None:
            return False
        if user["role"] == "admin":
            admin_count = db.execute(
                "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1"
            ).fetchone()["count"]
            if int(admin_count) <= 1:
                return False
        cursor = db.execute(
            "UPDATE users SET is_active = 0 WHERE id = ? AND is_active = 1",
            (user["id"],),
        )
        if cursor.rowcount == 0:
            return False
        db.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (int(time.time()), user["id"]),
        )
        return True


def reactivate_user(username: str) -> bool:
    with get_db() as db:
        cursor = db.execute(
            "UPDATE users SET is_active = 1 WHERE username = ? AND is_active = 0",
            (username.strip(),),
        )
    return cursor.rowcount > 0


def create_otp_entry(
    portal_name: str,
    display_name: str,
    secret: str,
    period: int,
    created_by: int,
) -> int:
    now = int(time.time())
    clean_portal_name = portal_name.strip()
    clean_secret = secret.strip().replace(" ", "")
    encrypted = encrypt_secret(clean_secret, clean_portal_name)
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO otp_entries
                (
                    portal_name, display_name, secret, secret_ciphertext,
                    secret_nonce, encryption_version, key_version, period,
                    is_active, created_by, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                clean_portal_name,
                display_name.strip(),
                ENCRYPTED_SECRET_PLACEHOLDER,
                encrypted["ciphertext"],
                encrypted["nonce"],
                encrypted["encryption_version"],
                encrypted["key_version"],
                period,
                created_by,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def list_otp_entries() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, portal_name, display_name, period, is_active, created_at, updated_at
            FROM otp_entries
            ORDER BY display_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_active_otp_entries() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, portal_name, display_name, period, is_active, created_at, updated_at
            FROM otp_entries
            WHERE is_active = 1
            ORDER BY display_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_active_otp_entries_for_user(user_id: int, now: int | None = None) -> list[dict]:
    current_time = int(time.time()) if now is None else now
    with get_db() as db:
        rows = db.execute(
            """
            SELECT DISTINCT p.id, p.portal_name, p.display_name, p.period,
                   p.is_active, p.created_at, p.updated_at
            FROM otp_entries AS p
            WHERE p.is_active = 1
              AND (
                EXISTS (
                    SELECT 1 FROM portal_grants AS g
                    WHERE g.portal_id = p.id AND g.user_id = ?
                      AND g.permission = 'read' AND g.is_active = 1
                      AND (g.expires_at IS NULL OR g.expires_at > ?)
                )
                OR EXISTS (
                    SELECT 1
                    FROM team_portal_grants AS tg
                    JOIN team_memberships AS tm ON tm.team_id = tg.team_id
                    JOIN teams AS t ON t.id = tm.team_id
                    WHERE tg.portal_id = p.id AND tm.user_id = ?
                      AND tg.permission = 'read' AND tg.is_active = 1
                      AND tm.is_active = 1 AND t.is_active = 1
                      AND (tg.expires_at IS NULL OR tg.expires_at > ?)
                )
              )
            ORDER BY p.display_name
            """,
            (user_id, current_time, user_id, current_time),
        ).fetchall()
    return [dict(row) for row in rows]


def get_otp_entry_by_portal(portal_name: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT
                id, portal_name, display_name, secret_ciphertext, secret_nonce,
                encryption_version, key_version, period, is_active, created_at, updated_at
            FROM otp_entries
            WHERE portal_name = ? AND is_active = 1
            """,
            (portal_name,),
        ).fetchone()
    return row_to_dict(row)


def get_otp_entry_by_portal_for_user(
    portal_name: str,
    user_id: int,
    now: int | None = None,
) -> dict | None:
    current_time = int(time.time()) if now is None else now
    with get_db() as db:
        row = db.execute(
            """
            SELECT
                p.id, p.portal_name, p.display_name, p.secret_ciphertext,
                p.secret_nonce, p.encryption_version, p.key_version,
                p.period, p.is_active, p.created_at, p.updated_at
            FROM otp_entries AS p
            WHERE p.portal_name = ?
              AND p.is_active = 1
              AND (
                EXISTS (
                    SELECT 1 FROM portal_grants AS g
                    WHERE g.portal_id = p.id AND g.user_id = ?
                      AND g.permission = 'read' AND g.is_active = 1
                      AND (g.expires_at IS NULL OR g.expires_at > ?)
                )
                OR EXISTS (
                    SELECT 1
                    FROM team_portal_grants AS tg
                    JOIN team_memberships AS tm ON tm.team_id = tg.team_id
                    JOIN teams AS t ON t.id = tm.team_id
                    WHERE tg.portal_id = p.id AND tm.user_id = ?
                      AND tg.permission = 'read' AND tg.is_active = 1
                      AND tm.is_active = 1 AND t.is_active = 1
                      AND (tg.expires_at IS NULL OR tg.expires_at > ?)
                )
              )
            """,
            (portal_name, user_id, current_time, user_id, current_time),
        ).fetchone()
    return row_to_dict(row)


def get_portal_by_name(portal_name: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT id, portal_name, is_active FROM otp_entries WHERE portal_name = ?",
            (portal_name,),
        ).fetchone()
    return row_to_dict(row)


def get_user_by_exact_username(username: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT id, username, is_active FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    return row_to_dict(row)


def create_portal_grant(
    portal_id: int,
    user_id: int,
    granted_by: int,
    permission: str,
    expires_at: int | None,
) -> int:
    now = int(time.time())
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO portal_grants
                (portal_id, user_id, permission, granted_by, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(portal_id, user_id, permission) DO UPDATE SET
                granted_by = excluded.granted_by,
                expires_at = excluded.expires_at,
                is_active = 1,
                created_at = excluded.created_at
            """,
            (portal_id, user_id, permission, granted_by, expires_at, now),
        )
        return int(cursor.lastrowid)


def revoke_portal_grant(portal_id: int, user_id: int, permission: str = "read") -> bool:
    with get_db() as db:
        cursor = db.execute(
            """
            UPDATE portal_grants SET is_active = 0
            WHERE portal_id = ? AND user_id = ? AND permission = ? AND is_active = 1
            """,
            (portal_id, user_id, permission),
        )
    return cursor.rowcount > 0


def list_portal_grants(portal_id: int | None = None) -> list[dict]:
    with get_db() as db:
        if portal_id is None:
            rows = db.execute(
                """
                SELECT g.id, g.portal_id, g.user_id, u.username, g.permission,
                       g.granted_by, g.expires_at, g.is_active, g.created_at
                FROM portal_grants AS g
                JOIN users AS u ON u.id = g.user_id
                ORDER BY g.created_at DESC
                """
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT g.id, g.portal_id, g.user_id, u.username, g.permission,
                       g.granted_by, g.expires_at, g.is_active, g.created_at
                FROM portal_grants AS g
                JOIN users AS u ON u.id = g.user_id
                WHERE g.portal_id = ?
                ORDER BY g.created_at DESC
                """,
                (portal_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def create_automation_client(
    name: str,
    owner_user_id: int,
    environment: str,
    expires_at: int | None,
) -> int:
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO automation_clients
                (name, owner_user_id, environment, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name.strip(), owner_user_id, environment.strip(), expires_at, int(time.time())),
        )
        return int(cursor.lastrowid)


def list_automation_clients() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT c.id, c.name, c.owner_user_id, u.username AS owner_username,
                   c.environment, c.status, c.created_at, c.expires_at
            FROM automation_clients AS c
            JOIN users AS u ON u.id = c.owner_user_id
            ORDER BY c.name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_automation_client(client_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT id, name, owner_user_id, environment, status, created_at, expires_at
            FROM automation_clients
            WHERE id = ?
            """,
            (client_id,),
        ).fetchone()
    return row_to_dict(row)


def revoke_automation_client(client_id: int) -> bool:
    with get_db() as db:
        cursor = db.execute(
            "UPDATE automation_clients SET status = 'revoked' WHERE id = ? AND status = 'active'",
            (client_id,),
        )
    return cursor.rowcount > 0


def create_api_credential(
    client_id: int,
    lookup_id: str,
    verifier_hash: str,
    expires_at: int | None,
) -> int:
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO api_credentials
                (client_id, lookup_id, verifier_hash, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (client_id, lookup_id, verifier_hash, int(time.time()), expires_at),
        )
        return int(cursor.lastrowid)


def list_api_credentials(client_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, created_at, expires_at, revoked_at, last_used_at
            FROM api_credentials
            WHERE client_id = ?
            ORDER BY created_at DESC
            """,
            (client_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_api_credential(credential_id: int, client_id: int) -> bool:
    with get_db() as db:
        cursor = db.execute(
            """
            UPDATE api_credentials SET revoked_at = ?
            WHERE id = ? AND client_id = ? AND revoked_at IS NULL
            """,
            (int(time.time()), credential_id, client_id),
        )
    return cursor.rowcount > 0


def get_client_credential(lookup_id: str, now: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT c.id AS client_id, c.name AS client_name, c.owner_user_id,
                   c.environment, c.status AS client_status, c.expires_at AS client_expires_at,
                   a.id AS credential_id, a.verifier_hash, a.expires_at,
                   a.revoked_at, a.last_used_at
            FROM api_credentials AS a
            JOIN automation_clients AS c ON c.id = a.client_id
            WHERE a.lookup_id = ?
              AND a.revoked_at IS NULL
              AND (a.expires_at IS NULL OR a.expires_at > ?)
              AND c.status = 'active'
              AND (c.expires_at IS NULL OR c.expires_at > ?)
            """,
            (lookup_id, now, now),
        ).fetchone()
    return row_to_dict(row)


def touch_api_credential(credential_id: int, now: int) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE api_credentials SET last_used_at = ? WHERE id = ?",
            (now, credential_id),
        )


def consume_client_rate_limit(client_id: int, now: int, limit: int) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT window_started_at, request_count FROM client_rate_limits WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if row is None or now - int(row["window_started_at"]) >= 60:
            db.execute(
                """
                INSERT INTO client_rate_limits (client_id, window_started_at, request_count)
                VALUES (?, ?, 1)
                ON CONFLICT(client_id) DO UPDATE SET
                    window_started_at = excluded.window_started_at,
                    request_count = excluded.request_count
                """,
                (client_id, now),
            )
            return True
        if int(row["request_count"]) >= limit:
            return False
        db.execute(
            "UPDATE client_rate_limits SET request_count = request_count + 1 WHERE client_id = ?",
            (client_id,),
        )
        return True


def create_client_portal_grant(
    client_id: int,
    portal_id: int,
    granted_by: int,
    expires_at: int | None,
) -> int:
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO client_portal_grants
                (client_id, portal_id, permission, granted_by, expires_at, created_at)
            VALUES (?, ?, 'read', ?, ?, ?)
            ON CONFLICT(client_id, portal_id, permission) DO UPDATE SET
                granted_by = excluded.granted_by,
                expires_at = excluded.expires_at,
                is_active = 1,
                created_at = excluded.created_at
            """,
            (client_id, portal_id, granted_by, expires_at, int(time.time())),
        )
        return int(cursor.lastrowid)


def get_client_portal_entry(
    client_id: int,
    portal_name: str,
    now: int | None = None,
) -> dict | None:
    current_time = int(time.time()) if now is None else now
    with get_db() as db:
        row = db.execute(
            """
            SELECT
                p.id, p.portal_name, p.display_name, p.secret_ciphertext,
                p.secret_nonce, p.encryption_version, p.key_version,
                p.period, p.is_active, p.created_at, p.updated_at
            FROM otp_entries AS p
            JOIN client_portal_grants AS g ON g.portal_id = p.id
            WHERE g.client_id = ?
              AND p.portal_name = ?
              AND p.is_active = 1
              AND g.permission = 'read'
              AND g.is_active = 1
              AND (g.expires_at IS NULL OR g.expires_at > ?)
            """,
            (client_id, portal_name, current_time),
        ).fetchone()
    return row_to_dict(row)


def create_team(name: str, created_by: int) -> int:
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO teams (name, created_by, created_at) VALUES (?, ?, ?)",
            (name.strip(), created_by, int(time.time())),
        )
        return int(cursor.lastrowid)


def get_team_by_name(name: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT id, name, created_by, is_active FROM teams WHERE name = ?",
            (name.strip(),),
        ).fetchone()
    return row_to_dict(row)


def list_teams() -> list[dict]:
    with get_db() as db:
        teams = db.execute(
            "SELECT id, name, created_by, is_active, created_at FROM teams ORDER BY name"
        ).fetchall()
        result = []
        for team in teams:
            members = db.execute(
                """
                SELECT u.username
                FROM team_memberships AS tm
                JOIN users AS u ON u.id = tm.user_id
                WHERE tm.team_id = ? AND tm.is_active = 1
                ORDER BY u.username
                """,
                (team["id"],),
            ).fetchall()
            item = dict(team)
            item["members"] = [row["username"] for row in members]
            result.append(item)
    return result


def add_team_member(team_id: int, user_id: int) -> None:
    with get_db() as db:
        db.execute(
            """
            INSERT INTO team_memberships (team_id, user_id, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(team_id, user_id) DO UPDATE SET is_active = 1
            """,
            (team_id, user_id, int(time.time())),
        )


def create_team_portal_grant(
    team_id: int,
    portal_id: int,
    granted_by: int,
    expires_at: int | None,
) -> int:
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO team_portal_grants
                (team_id, portal_id, permission, granted_by, expires_at, created_at)
            VALUES (?, ?, 'read', ?, ?, ?)
            ON CONFLICT(team_id, portal_id, permission) DO UPDATE SET
                granted_by = excluded.granted_by,
                expires_at = excluded.expires_at,
                is_active = 1,
                created_at = excluded.created_at
            """,
            (team_id, portal_id, granted_by, expires_at, int(time.time())),
        )
        return int(cursor.lastrowid)


def disable_otp_entry(portal_name: str) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE otp_entries SET is_active = 0, updated_at = ? WHERE portal_name = ?",
            (int(time.time()), portal_name),
        )


def reactivate_otp_entry(portal_name: str) -> bool:
    with get_db() as db:
        cursor = db.execute(
            """
            UPDATE otp_entries SET is_active = 1, updated_at = ?
            WHERE portal_name = ? AND is_active = 0
            """,
            (int(time.time()), portal_name),
        )
    return cursor.rowcount > 0


def update_otp_entry_metadata(portal_name: str, display_name: str, period: int) -> bool:
    with get_db() as db:
        cursor = db.execute(
            """
            UPDATE otp_entries
            SET display_name = ?, period = ?, updated_at = ?
            WHERE portal_name = ?
            """,
            (display_name.strip(), period, int(time.time()), portal_name),
        )
    return cursor.rowcount > 0


def delete_otp_entry(portal_name: str) -> None:
    with get_db() as db:
        db.execute("DELETE FROM otp_entries WHERE portal_name = ?", (portal_name,))
