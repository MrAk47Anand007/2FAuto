"""Single-writer vault lock and listener availability checks."""

import os
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.runtime.config import RuntimeConfig, RuntimeConfigError


@contextmanager
def instance_lock(data_dir: Path) -> Iterator[None]:
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = data_dir / "instance.lock"
    with open(lock_path, "a+b") as handle:
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeConfigError("Vault is already running") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeConfigError("Vault is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def ensure_port_available(config: RuntimeConfig) -> None:
    family = socket.AF_INET6 if ":" in config.host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((config.host, config.port))
        except OSError as exc:
            raise RuntimeConfigError(f"Runtime port {config.port} is unavailable") from exc
