import logging
import time
from contextlib import asynccontextmanager
from ipaddress import ip_address
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import create_user, get_user_by_username, init_database
from app.core.security import hash_password
from app.core.installation import is_configured, load_existing_keys
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.auth import api_router as auth_api_router
from app.routes.clients import router as clients_router
from app.routes.otp import router as otp_router
from app.routes.ui import router as ui_router
from app.routes.frontend import register_packaged_frontend
from app.routes.setup import router as setup_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def bootstrap_admin_user() -> None:
    """Create the configured admin only when its username is new."""
    # Bootstrap only when the configured username has never existed. A disabled
    # account must remain disabled across restarts and must not be recreated.
    if settings.APP_ENV == "packaged":
        return
    if get_user_by_username(settings.ADMIN_USERNAME, include_inactive=True) is None:
        create_user(
            settings.ADMIN_USERNAME,
            hash_password(settings.ADMIN_PASSWORD),
            "admin",
        )
        logger.info("Bootstrapped admin user %s", settings.ADMIN_USERNAME)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OTP service starting up")
    if settings.APP_ENV == "packaged":
        load_existing_keys()
    init_database()
    bootstrap_admin_user()
    yield
    logger.info("OTP service shutting down")


def create_app(*, packaged_ui_dir: Path | None = None) -> FastAPI:
    docs_url = "/docs" if settings.ENABLE_DOCS else None
    redoc_url = "/redoc" if settings.ENABLE_DOCS else None
    openapi_url = "/openapi.json" if settings.ENABLE_DOCS else None

    application = FastAPI(
        title="OTP Microservice",
        description="TOTP microservice for internal 2FA automation; review security plan before production use",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Request logging middleware
    # ------------------------------------------------------------------

    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Chromium's form POSTs use Origin: null under no-referrer, which
        # conflicts with strict CSRF origin validation. Keep origin information
        # for our own forms without sending referrers to other sites.
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        if settings.APP_ENV == "production" and settings.COOKIE_SECURE:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        if (
            request.url.path == "/otp"
            or request.url.path.startswith("/otp/")
            or request.url.path.startswith("/api/")
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    if settings.APP_ENV == "packaged":
        @application.middleware("http")
        async def setup_gate(request: Request, call_next):
            try:
                local_client = ip_address(request.client.host).is_loopback if request.client else False
            except ValueError:
                local_client = False
            path = request.url.path
            if path in {"/setup", "/api/setup/status", "/api/setup/initialize"} and not local_client:
                return JSONResponse(status_code=403, content={"detail": "Local setup only"})
            if not is_configured():
                if not local_client:
                    return JSONResponse(status_code=403, content={"detail": "Local setup only"})
                if path == "/":
                    return RedirectResponse("/setup", status_code=307)
                allowed = path in {
                    "/health", "/ready", "/api/setup/status", "/api/setup/initialize",
                    "/setup", "/favicon.png", "/robots.txt",
                } or path.startswith("/assets/")
                if not allowed:
                    return JSONResponse(status_code=503, content={"detail": "Setup required"})
                if path == "/api/setup/initialize":
                    origin = request.headers.get("origin")
                    expected = f"{request.url.scheme}://{request.url.netloc}"
                    if origin is not None and origin.rstrip("/") != expected:
                        return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
            response = await call_next(request)
            if request.url.path.startswith("/api/setup/"):
                response.headers["Cache-Control"] = "no-store"
            return response

    # ------------------------------------------------------------------
    # Global exception handler – never leak stack traces
    # ------------------------------------------------------------------

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------

    application.mount("/static", StaticFiles(directory="app/static"), name="static")
    application.include_router(auth_api_router if packaged_ui_dir is not None else auth_router)
    application.include_router(clients_router)
    application.include_router(admin_router)
    application.include_router(ui_router)
    application.include_router(otp_router)

    if packaged_ui_dir is not None:
        application.include_router(setup_router)
        register_packaged_frontend(application, packaged_ui_dir)

    return application


app = create_app()
