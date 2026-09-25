"""Command-line entry for the installed 2FAuto backend."""

import argparse
import getpass
import os
import sys
from pathlib import Path

from app.runtime.config import (RuntimeConfig, RuntimeConfigError, configure_https,
                                has_administrator, validate_https, write_config)
from app.runtime.lock import ensure_port_available, instance_lock


def default_ui_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "packaged-ui"
    return Path(__file__).resolve().parents[2] / "build" / "packaged-ui"


def read_recovery_passphrase() -> str:
    """Read a secret from a terminal or a secure stdin pipe without echoing it."""
    if sys.stdin.isatty():
        value = getpass.getpass("Recovery passphrase: ")
    else:
        value = sys.stdin.readline().rstrip("\r\n")
    if not value:
        raise RuntimeConfigError("Recovery passphrase is required")
    return value


def serve(config_path: Path, ui_dir: Path | None = None) -> None:
    config = RuntimeConfig.load(config_path)
    if (config.data_dir / "restore.pending").exists() or (config.data_dir / "migration.pending").exists():
        raise RuntimeConfigError("Vault recovery is incomplete; complete recovery before startup")
    selected_ui = (ui_dir or default_ui_dir()).resolve()
    if not selected_ui.is_absolute() or not (selected_ui / "index.html").is_file():
        raise RuntimeConfigError("Packaged web UI is missing")

    with instance_lock(config.data_dir):
        if config.tls_cert:
            if not has_administrator(config):
                raise RuntimeConfigError("Remote access requires a configured administrator")
            validate_https(config)
        ensure_port_available(config)
        os.environ["APP_ENV"] = "packaged"
        os.environ["TWOFAUTO_ROLE"] = config.role
        os.environ["TWOFAUTO_PACKAGED_DATA_DIR"] = str(config.data_dir)
        os.environ["DATABASE_PATH"] = str(config.database_path)
        os.environ["HOST"] = config.host
        os.environ["PORT"] = str(config.port)
        os.environ["ENABLE_DOCS"] = "false"
        os.environ["LEGACY_API_ENABLED"] = "false"
        os.environ["COOKIE_SECURE"] = "true" if config.tls_cert else "false"

        from app.main import create_app
        import uvicorn

        uvicorn.run(
            create_app(packaged_ui_dir=selected_ui),
            host=config.host,
            port=config.port,
            proxy_headers=False,
            access_log=False,
            ssl_certfile=str(config.tls_cert) if config.tls_cert else None,
            ssl_keyfile=str(config.tls_key) if config.tls_key else None,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="2FAuto installed runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="Create a non-secret role configuration")
    initialize.add_argument("--role", choices=["server", "desktop-web"], required=True)
    initialize.add_argument("--data-dir", type=Path, required=True)
    initialize.add_argument("--port", type=int, default=8765)
    initialize.add_argument("--if-missing", action="store_true", help="Keep an existing role configuration")
    run = commands.add_parser("serve", help="Start the configured backend")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--ui-dir", type=Path, help="Override the bundled UI for development")
    backup = commands.add_parser("backup", help="Create an encrypted recovery archive")
    backup.add_argument("--config", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore", help="Restore an archive to a new vault")
    restore.add_argument("--config", type=Path, required=True)
    restore.add_argument("--input", type=Path, required=True)
    legacy = commands.add_parser("import-legacy", help="Export a Compose vault to an encrypted archive")
    legacy.add_argument("--database", type=Path, required=True)
    legacy.add_argument("--env-file", type=Path, required=True)
    legacy.add_argument("--output", type=Path, required=True)
    network = commands.add_parser("configure-https", help="Enable HTTPS network access after setup")
    network.add_argument("--config", type=Path, required=True)
    network.add_argument("--bind", required=True)
    network.add_argument("--hostname", required=True)
    network.add_argument("--cert", type=Path, required=True)
    network.add_argument("--key", type=Path, required=True)
    migration = commands.add_parser("rollback-migration", help="Recover the pre-upgrade vault snapshot")
    migration.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "init":
            write_config(arguments.data_dir, role=arguments.role, port=arguments.port,
                         if_missing=arguments.if_missing)
        elif arguments.command == "serve":
            serve(arguments.config, arguments.ui_dir)
        elif arguments.command == "configure-https":
            config = RuntimeConfig.load(arguments.config)
            with instance_lock(config.data_dir):
                configure_https(arguments.config, host=arguments.bind,
                                hostname=arguments.hostname, cert=arguments.cert, key=arguments.key)
        elif arguments.command == "rollback-migration":
            from app.runtime.migration import restore_migration

            config = RuntimeConfig.load(arguments.config)
            with instance_lock(config.data_dir):
                restore_migration(config.data_dir)
        else:
            if arguments.command == "import-legacy":
                os.environ["APP_ENV"] = "packaged"
                from app.runtime.backup import import_legacy

                passphrase = read_recovery_passphrase()
                import_legacy(arguments.database, arguments.env_file, arguments.output, passphrase)
                print("Recovery operation completed")
                return 0
            config = RuntimeConfig.load(arguments.config)
            os.environ["APP_ENV"] = "packaged"
            os.environ["TWOFAUTO_ROLE"] = config.role
            from app.runtime.backup import create_backup, restore_backup

            passphrase = read_recovery_passphrase()
            if arguments.command == "backup":
                create_backup(config.data_dir, arguments.output, passphrase)
            else:
                with instance_lock(config.data_dir):
                    restore_backup(arguments.input, config.data_dir, passphrase)
            print("Recovery operation completed")
    except ValueError as exc:
        print(f"2FAuto runtime: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
