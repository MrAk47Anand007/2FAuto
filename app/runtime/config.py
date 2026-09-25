"""Non-secret, versioned configuration for installed runtime roles."""

import json
import os
import secrets
import sqlite3
import ssl
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Mapping

from cryptography import x509


class RuntimeConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    version: int
    role: str
    host: str
    port: int
    data_dir: Path
    tls_cert: Path | None = None
    tls_key: Path | None = None
    public_hostname: str | None = None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "otp_service.db"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "RuntimeConfig":
        base = {"version", "role", "host", "port", "data_dir"}
        tls_fields = {"tls_cert", "tls_key", "public_hostname"}
        if set(value) not in (base, base | tls_fields):
            raise RuntimeConfigError("Runtime configuration fields are invalid")
        if type(value["version"]) is not int or value["version"] != 1:
            raise RuntimeConfigError("Runtime configuration version is unsupported")
        if not isinstance(value["role"], str) or value["role"] not in {"server", "desktop-web"}:
            raise RuntimeConfigError("Runtime role must be server or desktop-web")
        if not isinstance(value["host"], str):
            raise RuntimeConfigError("Runtime host is invalid")
        try:
            address = ip_address(value["host"])
        except ValueError as exc:
            raise RuntimeConfigError("Runtime host must be an IP address") from exc
        if type(value["port"]) is not int or not 1024 <= value["port"] <= 65535:
            raise RuntimeConfigError("Runtime port must be between 1024 and 65535")
        if not isinstance(value["data_dir"], str) or not Path(value["data_dir"]).is_absolute():
            raise RuntimeConfigError("Runtime data directory must be absolute")
        directory = Path(value["data_dir"]).resolve()
        cert = key = None
        hostname = None
        if tls_fields <= set(value):
            if not all(isinstance(value[name], str) and value[name] for name in tls_fields):
                raise RuntimeConfigError("HTTPS certificate, key, and hostname are required")
            cert, key = Path(value["tls_cert"]), Path(value["tls_key"])
            hostname = str(value["public_hostname"])
            if not cert.is_absolute() or not key.is_absolute():
                raise RuntimeConfigError("HTTPS certificate and key paths must be absolute")
        if not address.is_loopback and (not cert or not key or not hostname):
            raise RuntimeConfigError("Remote listening requires configured HTTPS")
        return cls(1, str(value["role"]), str(value["host"]), int(value["port"]),
                   directory, cert, key, hostname)

    @classmethod
    def load(cls, path: Path) -> "RuntimeConfig":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            return cls.from_mapping(value)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise RuntimeConfigError("Runtime configuration cannot be loaded") from exc


def write_config(data_dir: Path, *, role: str, port: int = 8765, if_missing: bool = False) -> Path:
    directory = data_dir.resolve()
    config = RuntimeConfig.from_mapping({
        "version": 1, "role": role, "host": "127.0.0.1", "port": port,
        "data_dir": str(directory),
    })
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "runtime.json"
    if path.exists():
        if if_missing and RuntimeConfig.load(path).role == role:
            return path
        raise RuntimeConfigError("Runtime configuration already exists")
    if os.name == "nt" and role == "server":
        # Machine-scope DPAPI is safe only when other local users cannot read
        # the ciphertext. Run this while MSI still has administrative rights.
        subprocess.run([
            "icacls", str(directory), "/inheritance:r", "/grant:r",
            "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F",
            "*S-1-5-19:(OI)(CI)M",
        ], check=True, capture_output=True)
    if os.name != "nt":
        directory.chmod(0o700)
    temporary = directory / f"runtime.{secrets.token_hex(8)}.tmp"
    payload = json.dumps({
        "version": config.version, "role": config.role, "host": config.host,
        "port": config.port, "data_dir": str(config.data_dir),
    }, indent=2).encode("utf-8")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise RuntimeConfigError("Runtime configuration already exists") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return path


def has_administrator(config: RuntimeConfig) -> bool:
    if not (config.data_dir / "vault-keys.bin").is_file() or not config.database_path.is_file():
        return False
    try:
        with closing(sqlite3.connect(f"file:{config.database_path}?mode=ro", uri=True)) as db:
            return db.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone() is not None
    except sqlite3.Error:
        return False


def validate_https(config: RuntimeConfig) -> None:
    if not config.tls_cert or not config.tls_key or not config.public_hostname:
        raise RuntimeConfigError("HTTPS is not configured")
    try:
        cert = x509.load_pem_x509_certificate(config.tls_cert.read_bytes())
        if cert.not_valid_before_utc > datetime.now(timezone.utc) or cert.not_valid_after_utc <= datetime.now(timezone.utc):
            raise RuntimeConfigError("HTTPS certificate is not currently valid")
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        dns = names.get_values_for_type(x509.DNSName)
        ips = [str(value) for value in names.get_values_for_type(x509.IPAddress)]
        if config.public_hostname not in dns + ips:
            raise RuntimeConfigError("HTTPS certificate does not cover the public hostname")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(config.tls_cert), str(config.tls_key))
    except (OSError, ValueError, ssl.SSLError, x509.ExtensionNotFound) as exc:
        if isinstance(exc, RuntimeConfigError):
            raise
        raise RuntimeConfigError("HTTPS certificate or key is invalid") from exc


def configure_https(path: Path, *, host: str, hostname: str, cert: Path, key: Path) -> None:
    config = RuntimeConfig.load(path)
    if not has_administrator(config):
        raise RuntimeConfigError("Finish administrator setup before enabling network access")
    updated = RuntimeConfig.from_mapping({
        "version": 1, "role": config.role, "host": host, "port": config.port,
        "data_dir": str(config.data_dir), "tls_cert": str(cert.resolve()),
        "tls_key": str(key.resolve()), "public_hostname": hostname,
    })
    validate_https(updated)
    payload = json.dumps({
        "version": 1, "role": updated.role, "host": updated.host, "port": updated.port,
        "data_dir": str(updated.data_dir), "tls_cert": str(updated.tls_cert),
        "tls_key": str(updated.tls_key), "public_hostname": updated.public_hostname,
    }, indent=2).encode("utf-8")
    temporary = path.parent / f"runtime.{secrets.token_hex(8)}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
