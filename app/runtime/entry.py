"""Command-line entry for the installed 2FAuto backend."""

import argparse
import os
import sys
from pathlib import Path

from app.runtime.config import RuntimeConfig, RuntimeConfigError, write_config
from app.runtime.lock import ensure_port_available, instance_lock


def default_ui_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "packaged-ui"
    return Path(__file__).resolve().parents[2] / "build" / "packaged-ui"


def serve(config_path: Path, ui_dir: Path | None = None) -> None:
    config = RuntimeConfig.load(config_path)
    selected_ui = (ui_dir or default_ui_dir()).resolve()
    if not selected_ui.is_absolute() or not (selected_ui / "index.html").is_file():
        raise RuntimeConfigError("Packaged web UI is missing")

    with instance_lock(config.data_dir):
        ensure_port_available(config)
        os.environ["APP_ENV"] = "packaged"
        os.environ["TWOFAUTO_ROLE"] = config.role
        os.environ["TWOFAUTO_PACKAGED_DATA_DIR"] = str(config.data_dir)
        os.environ["DATABASE_PATH"] = str(config.database_path)
        os.environ["HOST"] = config.host
        os.environ["PORT"] = str(config.port)
        os.environ["ENABLE_DOCS"] = "false"
        os.environ["LEGACY_API_ENABLED"] = "false"

        from app.main import create_app
        import uvicorn

        uvicorn.run(
            create_app(packaged_ui_dir=selected_ui),
            host=config.host,
            port=config.port,
            proxy_headers=False,
            access_log=False,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="2FAuto installed runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="Create a non-secret role configuration")
    initialize.add_argument("--role", choices=["server", "desktop-web"], required=True)
    initialize.add_argument("--data-dir", type=Path, required=True)
    initialize.add_argument("--port", type=int, default=8765)
    run = commands.add_parser("serve", help="Start the configured backend")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--ui-dir", type=Path, help="Override the bundled UI for development")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "init":
            write_config(arguments.data_dir, role=arguments.role, port=arguments.port)
        else:
            serve(arguments.config, arguments.ui_dir)
    except RuntimeConfigError as exc:
        print(f"2FAuto runtime: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
