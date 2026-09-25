import json
import sqlite3
from contextlib import closing

import pytest
import pyotp


def test_encrypted_backup_restores_database_and_reprotects_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "packaged")
    from app.core.config import settings
    from app.core.installation import _decode_keys, _encode_keys, KEY_FILE
    from app.runtime.backup import create_backup, restore_backup, BackupError

    source = tmp_path / "original"
    source.mkdir()
    monkeypatch.setattr(settings, "PACKAGED_ROLE", "desktop-web")
    keys = {"SECRET_ENCRYPTION_KEY": "dGVzdA==", "SESSION_SECRET": "x" * 48}
    # Use a real 32-byte vault key.
    import base64
    keys["SECRET_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"k" * 32).decode()
    (source / KEY_FILE).write_bytes(_encode_keys(keys))
    db = source / "otp_service.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('recover me')")

    output = tmp_path / "recovery.2fauto"
    create_backup(source, output, "a long recovery passphrase")
    assert output.exists()
    assert b"recover me" not in output.read_bytes()
    assert b"SESSION_SECRET" not in output.read_bytes()
    with pytest.raises(BackupError, match="passphrase"):
        restore_backup(output, tmp_path / "wrong", "wrong passphrase")
    assert not (tmp_path / "wrong" / "otp_service.db").exists()

    target = tmp_path / "restored"
    target.mkdir()
    with closing(sqlite3.connect(target / "otp_service.db")) as connection:
        connection.execute("CREATE TABLE users (username TEXT)")
        connection.commit()
    restore_backup(output, target, "a long recovery passphrase")
    assert _decode_keys((target / KEY_FILE).read_bytes()) == keys
    with sqlite3.connect(target / "otp_service.db") as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "recover me"
    with pytest.raises(BackupError, match="already"):
        restore_backup(output, target, "a long recovery passphrase")


def test_backup_rejects_missing_key_and_existing_destination(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "packaged")
    from app.runtime.backup import create_backup, BackupError

    source = tmp_path / "vault"
    source.mkdir()
    with sqlite3.connect(source / "otp_service.db") as connection:
        connection.execute("CREATE TABLE sample (id INTEGER)")
    with pytest.raises(BackupError, match="key"):
        create_backup(source, tmp_path / "out.2fauto", "passphrase")
    (tmp_path / "out.2fauto").write_bytes(b"existing")
    with pytest.raises(BackupError, match="already"):
        create_backup(source, tmp_path / "out.2fauto", "passphrase")


def test_legacy_import_recovers_totp_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "packaged")
    from app.core.config import settings
    from app.core.secrets import encrypt_secret, decrypt_secret
    from app.runtime.backup import import_legacy, restore_backup
    import base64

    key = base64.urlsafe_b64encode(b"z" * 32).decode()
    settings.SECRET_ENCRYPTION_KEY = key
    settings.SECRET_ENCRYPTION_KEY_VERSION = "v1"
    settings.SECRET_ENCRYPTION_KEYS = ""
    seed = pyotp.random_base32()
    encrypted = encrypt_secret(seed, "portal")
    legacy = tmp_path / "old.db"
    with sqlite3.connect(legacy) as connection:
        connection.execute("CREATE TABLE sample (ciphertext TEXT, nonce TEXT, version INTEGER, key_version TEXT)")
        connection.execute("INSERT INTO sample VALUES (?, ?, ?, ?)", (
            encrypted["ciphertext"], encrypted["nonce"], encrypted["encryption_version"],
            encrypted["key_version"],
        ))
    env_file = tmp_path / "old.env"
    env_file.write_text(f"SECRET_ENCRYPTION_KEY={key}\nSESSION_SECRET={'x' * 48}\n", encoding="utf-8")
    archive = tmp_path / "import.2fauto"
    import_legacy(legacy, env_file, archive, "a long recovery passphrase")
    target = tmp_path / "new-vault"
    restore_backup(archive, target, "a long recovery passphrase")
    with sqlite3.connect(target / "otp_service.db") as connection:
        row = connection.execute("SELECT * FROM sample").fetchone()
    settings.SECRET_ENCRYPTION_KEY = ""
    settings.SESSION_SECRET = ""
    monkeypatch.setattr(settings, "PACKAGED_DATA_DIR", str(target))
    from app.core.installation import load_existing_keys
    assert load_existing_keys()
    restored_seed = decrypt_secret(row[0], row[1], "portal", row[2], row[3])
    assert pyotp.TOTP(restored_seed).at(1700000000) == pyotp.TOTP(seed).at(1700000000)
