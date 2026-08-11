import sqlite3
import time
from pathlib import Path

from app.core.config import settings


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
                secret TEXT NOT NULL,
                period INTEGER NOT NULL DEFAULT 30,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );
            """
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


def get_user_by_username(username: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username.strip(),),
        ).fetchone()
    return row_to_dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


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
    user = get_user_by_username(username)
    if user is None:
        return False
    if user["role"] == "admin" and active_admin_count() <= 1:
        return False
    with get_db() as db:
        db.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
    return True


def create_otp_entry(
    portal_name: str,
    display_name: str,
    secret: str,
    period: int,
    created_by: int,
) -> int:
    now = int(time.time())
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO otp_entries
                (portal_name, display_name, secret, period, is_active, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                portal_name.strip(),
                display_name.strip(),
                secret.strip().replace(" ", ""),
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
            SELECT id, portal_name, display_name, secret, period, is_active, created_at, updated_at
            FROM otp_entries
            ORDER BY display_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_active_otp_entries() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, portal_name, display_name, secret, period, is_active, created_at, updated_at
            FROM otp_entries
            WHERE is_active = 1
            ORDER BY display_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_otp_entry_by_portal(portal_name: str) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT id, portal_name, display_name, secret, period, is_active, created_at, updated_at
            FROM otp_entries
            WHERE portal_name = ? AND is_active = 1
            """,
            (portal_name,),
        ).fetchone()
    return row_to_dict(row)


def disable_otp_entry(portal_name: str) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE otp_entries SET is_active = 0, updated_at = ? WHERE portal_name = ?",
            (int(time.time()), portal_name),
        )


def delete_otp_entry(portal_name: str) -> None:
    with get_db() as db:
        db.execute("DELETE FROM otp_entries WHERE portal_name = ?", (portal_name,))
