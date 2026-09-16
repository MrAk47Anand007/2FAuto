"""Create a consistent SQLite backup without copying a live file directly."""

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    if source == destination:
        raise SystemExit("Source and destination must be different")
    if not source.exists():
        raise SystemExit(f"Source database does not exist: {source}")
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite existing backup: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)
    print(destination)


if __name__ == "__main__":
    main()
