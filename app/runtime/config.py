"""Non-secret, versioned configuration for installed runtime roles."""

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class RuntimeConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    version: int
    role: str
    host: str
    port: int
    data_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "otp_service.db"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "RuntimeConfig":
        if set(value) != {"version", "role", "host", "port", "data_dir"}:
            raise RuntimeConfigError("Runtime configuration fields are invalid")
        if type(value["version"]) is not int or value["version"] != 1:
            raise RuntimeConfigError("Runtime configuration version is unsupported")
        if not isinstance(value["role"], str) or value["role"] not in {"server", "desktop-web"}:
            raise RuntimeConfigError("Runtime role must be server or desktop-web")
        if not isinstance(value["host"], str) or value["host"] not in {"127.0.0.1", "::1"}:
            raise RuntimeConfigError("Remote listening requires configured HTTPS")
        if type(value["port"]) is not int or not 1024 <= value["port"] <= 65535:
            raise RuntimeConfigError("Runtime port must be between 1024 and 65535")
        if not isinstance(value["data_dir"], str) or not Path(value["data_dir"]).is_absolute():
            raise RuntimeConfigError("Runtime data directory must be absolute")
        directory = Path(value["data_dir"]).resolve()
        return cls(1, str(value["role"]), str(value["host"]), int(value["port"]), directory)

    @classmethod
    def load(cls, path: Path) -> "RuntimeConfig":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            return cls.from_mapping(value)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise RuntimeConfigError("Runtime configuration cannot be loaded") from exc


def write_config(data_dir: Path, *, role: str, port: int = 8765) -> Path:
    directory = data_dir.resolve()
    config = RuntimeConfig.from_mapping({
        "version": 1, "role": role, "host": "127.0.0.1", "port": port,
        "data_dir": str(directory),
    })
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    path = directory / "runtime.json"
    if path.exists():
        raise RuntimeConfigError("Runtime configuration already exists")
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
