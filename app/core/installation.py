"""First-run key storage and single-use administrator setup for packaged mode."""

import base64
import binascii
import ctypes
import json
import os
import secrets
import sqlite3
import time
from ctypes import wintypes
from pathlib import Path

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password


KEY_FILE = "vault-keys.bin"
FILE_VERSION = b"2FAUTO1"


class InstallationError(ValueError):
    pass


def packaged_data_dir() -> Path:
    return Path(settings.PACKAGED_DATA_DIR).resolve()


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    source_buffer = ctypes.create_string_buffer(data)
    source = DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if protect:
        operation = crypt32.CryptProtectData
        operation.argtypes = [ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
        flags = 0x1 | (0x4 if settings.PACKAGED_ROLE == "server" else 0)
        args = (ctypes.byref(source), "2FAuto vault keys", None, None, None, flags, ctypes.byref(target))
    else:
        operation = crypt32.CryptUnprotectData
        operation.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
        args = (ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(target))
    operation.restype = wintypes.BOOL
    if not operation(*args):
        raise InstallationError(f"Windows key protection failed: {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


def _encode_keys(values: dict[str, str]) -> bytes:
    data = json.dumps(values, separators=(",", ":")).encode("utf-8")
    if os.name == "nt":
        return FILE_VERSION + b"W" + _dpapi(data, protect=True)
    return FILE_VERSION + b"P" + data


def _decode_keys(data: bytes) -> dict[str, str]:
    if not data.startswith(FILE_VERSION):
        raise InstallationError("Key file format is not supported")
    mode, payload = data[len(FILE_VERSION):len(FILE_VERSION) + 1], data[len(FILE_VERSION) + 1:]
    if mode == b"W" and os.name == "nt":
        payload = _dpapi(payload, protect=False)
    elif mode != b"P" or os.name == "nt":
        raise InstallationError("Key file protection does not match this system")
    try:
        values = json.loads(payload)
        encryption_key = base64.urlsafe_b64decode(values["SECRET_ENCRYPTION_KEY"])
        if len(encryption_key) != 32 or len(values["SESSION_SECRET"]) < 32:
            raise ValueError
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error) as exc:
        raise InstallationError("Key file is invalid") from exc
    return values


def load_existing_keys() -> bool:
    path = packaged_data_dir() / KEY_FILE
    if not path.is_file():
        return False
    values = _decode_keys(path.read_bytes())
    settings.SECRET_ENCRYPTION_KEY = values["SECRET_ENCRYPTION_KEY"]
    settings.SESSION_SECRET = values["SESSION_SECRET"]
    return True


def _create_keys() -> None:
    directory = packaged_data_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    values = {
        "SECRET_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
        "SESSION_SECRET": secrets.token_urlsafe(48),
    }
    path = directory / KEY_FILE
    temporary = directory / f"{KEY_FILE}.{secrets.token_hex(8)}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(_encode_keys(values))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            load_existing_keys()
            return
    except Exception:
        raise
    finally:
        temporary.unlink(missing_ok=True)
    settings.SECRET_ENCRYPTION_KEY = values["SECRET_ENCRYPTION_KEY"]
    settings.SESSION_SECRET = values["SESSION_SECRET"]


def is_configured() -> bool:
    if not settings.SECRET_ENCRYPTION_KEY or not settings.SESSION_SECRET:
        return False
    if not (packaged_data_dir() / KEY_FILE).is_file():
        return False
    try:
        with get_db() as db:
            row = db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone()
            return row is not None
    except sqlite3.OperationalError:
        return False


def initialize_administrator(username: str, password: str) -> None:
    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone():
            raise InstallationError("The vault already has an administrator")
        if not (packaged_data_dir() / KEY_FILE).exists():
            has_data = db.execute("SELECT 1 FROM users LIMIT 1").fetchone() or db.execute(
                "SELECT 1 FROM otp_entries LIMIT 1"
            ).fetchone()
            if has_data:
                raise InstallationError("Existing data needs its original encryption key")
            _create_keys()
        else:
            load_existing_keys()
        db.execute(
            "INSERT INTO users (username, password_hash, role, is_active, created_at) "
            "VALUES (?, ?, 'admin', 1, ?)",
            (username.strip(), hash_password(password), int(time.time())),
        )
