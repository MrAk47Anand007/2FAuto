"""Same-machine rollback snapshot taken before packaged schema changes."""

import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from app.core.installation import KEY_FILE
from app.runtime.config import RuntimeConfigError


SCHEMA_VERSION = 1
MARKER = "migration.pending"


def prepare_migration(data_dir: Path, database_path: Path | None = None) -> bool:
    database = database_path or data_dir / "otp_service.db"
    marker = data_dir / MARKER
    if marker.exists():
        raise RuntimeConfigError("An interrupted migration needs recovery before startup")
    if not database.is_file():
        return False
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeConfigError("This vault needs a newer 2FAuto version")
        if current == SCHEMA_VERSION:
            return False
        key = data_dir / KEY_FILE
        if not key.is_file():
            raise RuntimeConfigError("The original vault key is required before migration")
        backup = data_dir / "pre-upgrade" / f"{int(time.time())}-{secrets.token_hex(4)}"
        backup.mkdir(mode=0o700, parents=True)
        if os.name != "nt":
            backup.chmod(0o700)
        snapshot = backup / "otp_service.db"
        with closing(sqlite3.connect(snapshot)) as copy:
            connection.backup(copy)
        stored_key = backup / KEY_FILE
        stored_key.write_bytes(key.read_bytes())
        if os.name != "nt":
            snapshot.chmod(0o600)
            stored_key.chmod(0o600)
        with marker.open("x", encoding="ascii") as handle:
            handle.write(backup.name)
            handle.flush()
            os.fsync(handle.fileno())
    return True


def complete_migration(data_dir: Path, database_path: Path | None = None) -> None:
    database = database_path or data_dir / "otp_service.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
    (data_dir / MARKER).unlink(missing_ok=True)


def restore_migration(data_dir: Path) -> None:
    marker = data_dir / MARKER
    if not marker.is_file():
        raise RuntimeConfigError("No interrupted migration was found")
    backup_name = marker.read_text(encoding="ascii").strip()
    if not backup_name or Path(backup_name).name != backup_name:
        raise RuntimeConfigError("Migration marker is invalid")
    backup = data_dir / "pre-upgrade" / backup_name
    source_db = backup / "otp_service.db"
    source_key = backup / KEY_FILE
    if not source_db.is_file() or not source_key.is_file():
        raise RuntimeConfigError("Migration backup is incomplete")
    restored_db = data_dir / f"restore-{secrets.token_hex(8)}.db"
    restored_key = data_dir / f"restore-{secrets.token_hex(8)}.key"
    try:
        restored_db.write_bytes(source_db.read_bytes())
        restored_key.write_bytes(source_key.read_bytes())
        if os.name != "nt":
            restored_db.chmod(0o600)
            restored_key.chmod(0o600)
        with closing(sqlite3.connect(restored_db)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeConfigError("Migration backup database is damaged")
        os.replace(restored_key, data_dir / KEY_FILE)
        os.replace(restored_db, data_dir / "otp_service.db")
        marker.unlink()
    finally:
        restored_db.unlink(missing_ok=True)
        restored_key.unlink(missing_ok=True)
