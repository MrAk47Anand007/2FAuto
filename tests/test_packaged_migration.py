import sqlite3
from contextlib import closing

import pytest


def test_pre_upgrade_snapshot_survives_failed_migration(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "packaged")
    from app.runtime.config import RuntimeConfigError
    from app.runtime.migration import (prepare_migration, complete_migration,
                                       restore_migration)

    data_dir = tmp_path / "vault"
    data_dir.mkdir()
    database = data_dir / "otp_service.db"
    key = data_dir / "vault-keys.bin"
    key.write_bytes(b"protected original key")
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('before upgrade')")
        connection.commit()

    assert prepare_migration(data_dir)
    assert (data_dir / "migration.pending").exists()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE sample SET value='partial upgrade'")
        connection.commit()
    with pytest.raises(RuntimeConfigError, match="interrupted"):
        prepare_migration(data_dir)
    restore_migration(data_dir)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "before upgrade"
    assert key.read_bytes() == b"protected original key"
    assert not (data_dir / "migration.pending").exists()

    assert prepare_migration(data_dir)
    complete_migration(data_dir)
    assert prepare_migration(data_dir) is False
