"""Loopback-only, single-use packaged installation setup API."""

import hmac
import secrets

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core.installation import InstallationError, initialize_administrator, is_configured


router = APIRouter()
_setup_token = secrets.token_urlsafe(32)


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("password")
    @classmethod
    def reject_sample_password(cls, value: str) -> str:
        if value.lower() in {"change-this-admin-password", "password123456", "adminpassword123"}:
            raise ValueError("Choose a unique administrator password")
        return value


@router.get("/api/setup/status")
def setup_status() -> dict:
    if is_configured():
        return {"configured": True}
    return {"configured": False, "setup_token": _setup_token}


@router.post("/api/setup/initialize", status_code=201)
def initialize(body: SetupRequest, x_setup_token: str | None = Header(default=None)) -> JSONResponse:
    if is_configured():
        raise HTTPException(status_code=409, detail="The vault is already configured")
    if not x_setup_token or not hmac.compare_digest(x_setup_token, _setup_token):
        raise HTTPException(status_code=403, detail="Setup token is invalid")
    try:
        initialize_administrator(body.username, body.password)
    except InstallationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"configured": True}, status_code=201)
