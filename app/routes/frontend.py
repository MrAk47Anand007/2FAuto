from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def register_packaged_frontend(application: FastAPI, ui_dir: Path) -> None:
    """Serve the packaged React shell and assets without intercepting API paths."""
    shell = ui_dir / "index.html"
    if not shell.is_file():
        raise ValueError(f"Packaged UI shell is missing: {shell}")

    assets = ui_dir / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="packaged-assets")

    def fixed_file_response(path: Path):
        def serve() -> FileResponse:
            return FileResponse(path)

        return serve

    for filename in ("favicon.png", "robots.txt"):
        static_path = ui_dir / filename
        if static_path.is_file():
            application.add_api_route(
                f"/{filename}",
                fixed_file_response(static_path),
                methods=["GET"],
                include_in_schema=False,
            )

    def serve_shell() -> FileResponse:
        return FileResponse(shell, media_type="text/html")

    for path in ("/", "/setup", "/login", "/app", "/app/{path:path}"):
        application.add_api_route(path, serve_shell, methods=["GET"], include_in_schema=False)
