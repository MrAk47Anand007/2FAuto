"""Passphrase-encrypted, portable SQLite and key archive for installed vaults."""

import io
import base64
import binascii
import json
import os
import secrets
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path
from dotenv import dotenv_values

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.core.installation import KEY_FILE, _decode_keys, _encode_keys


MAGIC = b"2FAUTO-BACKUP-1\0"
DATABASE = "otp_service.db"
RESTORE_MARKER = "restore.pending"


class BackupError(ValueError):
    pass


def _derive(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 12:
        raise BackupError("Recovery passphrase must be at least 12 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def create_backup(data_dir: Path, destination: Path, passphrase: str) -> Path:
    """Snapshot SQLite while it is live and encrypt the matching vault keys."""
    if destination.exists():
        raise BackupError("Backup destination already exists")
    source_db = data_dir / DATABASE
    source_key = data_dir / KEY_FILE
    if not source_key.is_file():
        raise BackupError("The vault key file is missing")
    if not source_db.is_file():
        raise BackupError("The vault database is missing")
    try:
        keys = _decode_keys(source_key.read_bytes())
    except Exception as exc:
        raise BackupError("The vault key file cannot be read") from exc

    salt = secrets.token_bytes(16)
    key = _derive(passphrase, salt)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="2fauto-backup-") as temporary:
        snapshot = Path(temporary) / DATABASE
        with closing(sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)) as original, \
                closing(sqlite3.connect(snapshot)) as copy:
            original.backup(copy)
        with closing(sqlite3.connect(snapshot)) as checked:
            if checked.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("Database integrity check failed")
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, DATABASE)
            archive.writestr("keys.json", json.dumps(keys, separators=(",", ":")))
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(nonce, payload.getvalue(), MAGIC)
        temporary_output = destination.parent / f".{destination.name}.{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(temporary_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(MAGIC + salt + nonce + ciphertext)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary_output, destination)
        except FileExistsError as exc:
            raise BackupError("Backup destination already exists") from exc
        finally:
            temporary_output.unlink(missing_ok=True)
    return destination


def restore_backup(archive_path: Path, data_dir: Path, passphrase: str) -> Path:
    """Restore into a new vault directory, re-protecting keys for this OS account."""
    destination_db = data_dir / DATABASE
    destination_key = data_dir / KEY_FILE
    if destination_key.exists():
        raise BackupError("A vault already exists at the restore destination")
    if destination_db.exists():
        try:
            with closing(sqlite3.connect(f"file:{destination_db}?mode=ro", uri=True)) as existing:
                tables = [row[0] for row in existing.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'"
                )]
                for table in tables:
                    quoted = table.replace('"', '""')
                    if existing.execute(f'SELECT 1 FROM "{quoted}" LIMIT 1').fetchone():
                        raise BackupError("A vault already exists at the restore destination")
        except sqlite3.Error as exc:
            raise BackupError("Existing database cannot be checked before restore") from exc
    raw = archive_path.read_bytes()
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 16 + 12 + 16:
        raise BackupError("Recovery archive format is invalid")
    offset = len(MAGIC)
    salt, nonce = raw[offset:offset + 16], raw[offset + 16:offset + 28]
    try:
        plaintext = AESGCM(_derive(passphrase, salt)).decrypt(nonce, raw[offset + 28:], MAGIC)
    except InvalidTag as exc:
        raise BackupError("Recovery passphrase is wrong or archive is damaged") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(plaintext)) as archive:
            if set(archive.namelist()) != {DATABASE, "keys.json"}:
                raise BackupError("Recovery archive contents are invalid")
            keys = json.loads(archive.read("keys.json"))
            protected_keys = _encode_keys(keys)
            database_bytes = archive.read(DATABASE)
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError) as exc:
        raise BackupError("Recovery archive contents are invalid") from exc

    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        data_dir.chmod(0o700)
    marker = data_dir / RESTORE_MARKER
    marker.write_text("Restore in progress", encoding="ascii")
    with tempfile.TemporaryDirectory(dir=data_dir, prefix="restore-") as temporary:
        staged_db = Path(temporary) / DATABASE
        staged_key = Path(temporary) / KEY_FILE
        staged_db.write_bytes(database_bytes)
        staged_key.write_bytes(protected_keys)
        if os.name != "nt":
            staged_db.chmod(0o600)
            staged_key.chmod(0o600)
        with closing(sqlite3.connect(staged_db)) as checked:
            if checked.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("Restored database integrity check failed")
        os.replace(staged_key, destination_key)
        os.replace(staged_db, destination_db)
    marker.unlink()
    return data_dir


def import_legacy(database: Path, env_file: Path, destination: Path, passphrase: str) -> Path:
    """Export an existing Compose vault to the portable recovery format."""
    values = dotenv_values(env_file, interpolate=False)
    encryption_key = values.get("SECRET_ENCRYPTION_KEY")
    session_secret = values.get("SESSION_SECRET")
    try:
        if not encryption_key or len(base64.urlsafe_b64decode(encryption_key)) != 32:
            raise ValueError
        if not session_secret or len(session_secret) < 32:
            raise ValueError
    except (ValueError, TypeError, binascii.Error) as exc:
        raise BackupError("Existing deployment keys are incomplete") from exc
    keys = {
        "SECRET_ENCRYPTION_KEY": encryption_key,
        "SESSION_SECRET": session_secret,
        "SECRET_ENCRYPTION_KEY_VERSION": values.get("SECRET_ENCRYPTION_KEY_VERSION") or "v1",
        "SECRET_ENCRYPTION_KEYS": values.get("SECRET_ENCRYPTION_KEYS") or "",
    }
    if keys["SECRET_ENCRYPTION_KEYS"]:
        try:
            rotated = json.loads(keys["SECRET_ENCRYPTION_KEYS"])
            if not isinstance(rotated, dict):
                raise ValueError
            for value in rotated.values():
                if len(base64.urlsafe_b64decode(value)) != 32:
                    raise ValueError
        except (ValueError, TypeError, binascii.Error) as exc:
            raise BackupError("Existing deployment key rotation data is invalid") from exc
    with tempfile.TemporaryDirectory(prefix="2fauto-import-") as temporary:
        temporary_dir = Path(temporary)
        (temporary_dir / KEY_FILE).write_bytes(_encode_keys(keys))
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as original, \
                closing(sqlite3.connect(temporary_dir / DATABASE)) as copy:
            original.backup(copy)
        return create_backup(temporary_dir, destination, passphrase)
