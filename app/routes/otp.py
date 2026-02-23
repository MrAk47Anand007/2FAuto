import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core import totp as totp_core
from app.middleware.auth import require_api_key, require_hmac_signature

router = APIRouter()


class VerifyRequest(BaseModel):
    otp: str


# ---------------------------------------------------------------------------
# GET /health  – public
# ---------------------------------------------------------------------------

@router.get("/health", tags=["Health"])
def health_check() -> dict:
    return {"status": "ok", "timestamp": int(time.time())}


# ---------------------------------------------------------------------------
# GET /otp  – API-key protected
# ---------------------------------------------------------------------------

@router.get("/otp", tags=["OTP"], dependencies=[Depends(require_api_key)])
def get_otp() -> dict:
    return totp_core.get_otp()


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
    return totp_core.get_otp()
