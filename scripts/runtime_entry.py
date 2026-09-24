"""Frozen executable entry point; keep imports after runtime config is loaded."""

from app.runtime.entry import main


if __name__ == "__main__":
    raise SystemExit(main())
