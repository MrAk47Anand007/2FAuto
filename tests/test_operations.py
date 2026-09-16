import sqlite3
import subprocess
import sys


def test_sqlite_backup_and_restore_scripts_preserve_data(tmp_path):
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"

    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        db.execute("INSERT INTO values_table (value) VALUES ('synthetic')")

    subprocess.run(
        [sys.executable, "scripts/backup_sqlite.py", str(source), str(backup)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "scripts/restore_sqlite.py", str(backup), str(restored)],
        check=True,
        capture_output=True,
        text=True,
    )

    with sqlite3.connect(restored) as db:
        row = db.execute("SELECT value FROM values_table").fetchone()
    assert row == ("synthetic",)
