"""Restore a SQLite backup into a new database file."""

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    backup = args.backup.resolve()
    destination = args.destination.resolve()
    if not backup.exists():
        raise SystemExit(f"Backup does not exist: {backup}")
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite existing database: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as backup_db, sqlite3.connect(destination) as restored_db:
        backup_db.backup(restored_db)
    print(destination)


if __name__ == "__main__":
    main()
