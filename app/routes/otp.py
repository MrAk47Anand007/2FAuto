import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import totp as totp_core
from app.core.database import get_db
from app.core.secrets import SecretEncryptionError
from app.core.config import settings
from app.middleware.auth import require_api_key, require_hmac_signature
from app.services.otp import (
    PortalNotFound,
    get_portal_otp as issue_portal_otp,
    issue_legacy_otp,
)

router = APIRouter()


class VerifyRequest(BaseModel):
    otp: str


# ---------------------------------------------------------------------------
# GET /health  – public
# ---------------------------------------------------------------------------

@router.get("/health", tags=["Health"])
def health_check() -> dict:
    return {"status": "ok", "timestamp": int(time.time())}


@router.get("/ready", tags=["Health"])
def readiness_check() -> dict:
    try:
        with get_db() as db:
            db.execute("SELECT 1").fetchone()
        if not settings.SECRET_ENCRYPTION_KEY:
            raise SecretEncryptionError("Secret encryption is not configured")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service is not ready") from exc
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# GET /otp  – API-key protected
# ---------------------------------------------------------------------------

@router.get("/otp", tags=["OTP"], dependencies=[Depends(require_api_key)])
def get_otp() -> dict:
    return issue_legacy_otp()


# ---------------------------------------------------------------------------
# POST /otp/verify  – API-key protected
# ---------------------------------------------------------------------------

@router.post("/otp/verify", tags=["OTP"], dependencies=[Depends(require_api_key)])
def verify_otp(body: VerifyRequest) -> dict:
    valid = totp_core.verify_otp(body.otp)
    return {"valid": valid, "timestamp": int(time.time())}


# ---------------------------------------------------------------------------
# GET /otp/secure  – API-key + HMAC signature protected
# ---------------------------------------------------------------------------

@router.get(
    "/otp/secure",
    tags=["OTP"],
    dependencies=[Depends(require_hmac_signature)],
)
def get_otp_secure() -> dict:
    return issue_legacy_otp()


@router.get("/otp/{portal_name}", tags=["OTP"], dependencies=[Depends(require_api_key)])
def get_portal_otp(portal_name: str) -> dict:
    try:
        return issue_portal_otp(portal_name)
    except PortalNotFound as exc:
        raise HTTPException(status_code=404, detail="OTP portal not found") from exc
