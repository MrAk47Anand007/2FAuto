import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import create_user, get_user_by_username, init_database
from app.core.security import hash_password
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.otp import router as otp_router
from app.routes.ui import router as ui_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OTP service starting up")
    init_database()
    if get_user_by_username(settings.ADMIN_USERNAME) is None:
        create_user(
            settings.ADMIN_USERNAME,
            hash_password(settings.ADMIN_PASSWORD),
            "admin",
        )
        logger.info("Bootstrapped admin user %s", settings.ADMIN_USERNAME)
    yield
    logger.info("OTP service shutting down")


def create_app() -> FastAPI:
    docs_url = "/docs" if settings.ENABLE_DOCS else None
    redoc_url = "/redoc" if settings.ENABLE_DOCS else None
    openapi_url = "/openapi.json" if settings.ENABLE_DOCS else None

    application = FastAPI(
        title="OTP Microservice",
        description="Production-ready TOTP microservice for internal 2FA automation",
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
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(ui_router)
    application.include_router(otp_router)

    return application


app = create_app()
