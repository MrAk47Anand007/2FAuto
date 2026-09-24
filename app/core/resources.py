"""Resolve application resources from source or a frozen executable."""

import sys
from pathlib import Path


def app_resource(*parts: str) -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    app_root = Path(bundled) / "app" if bundled else Path(__file__).resolve().parents[1]
    return app_root.joinpath(*parts)
