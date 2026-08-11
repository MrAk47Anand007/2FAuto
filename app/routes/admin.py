import re
import sqlite3

import pyotp
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.database import (
    create_otp_entry,
    create_user,
    delete_otp_entry,
    disable_otp_entry,
    disable_user,
    list_otp_entries,
    list_users,
)
from app.core.security import hash_password, require_admin

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")
PORTAL_NAME_RE = re.compile(r"^[a-z0-9-]{2,64}$")


def mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request):
    admin = require_admin(request)
    portals = [
        {**portal, "masked_secret": mask_secret(portal["secret"])}
        for portal in list_otp_entries()
    ]
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": admin,
            "portals": portals,
            "users": list_users(),
            "error": None,
        },
    )


@router.post("/portals")
def add_portal(
    request: Request,
    portal_name: str = Form(...),
    display_name: str = Form(...),
    secret: str = Form(...),
    period: int = Form(30),
):
    admin = require_admin(request)
    portal_name = portal_name.strip().lower()
    clean_secret = secret.strip().replace(" ", "")

    if not PORTAL_NAME_RE.match(portal_name):
        raise HTTPException(status_code=400, detail="Portal name must use lowercase letters, numbers, and hyphens")
    if period < 10 or period > 120:
        raise HTTPException(status_code=400, detail="Period must be between 10 and 120 seconds")
    try:
        pyotp.TOTP(clean_secret, interval=period).now()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Secret must be a valid base32 TOTP secret") from exc

    try:
        create_otp_entry(portal_name, display_name, clean_secret, period, admin["id"])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Portal name already exists") from exc

    return RedirectResponse("/admin", status_code=303)


@router.post("/portals/{portal_name}/disable")
def disable_portal(request: Request, portal_name: str):
    require_admin(request)
    disable_otp_entry(portal_name)
    return RedirectResponse("/admin", status_code=303)


@router.post("/portals/{portal_name}/delete")
def delete_portal(request: Request, portal_name: str):
    require_admin(request)
    delete_otp_entry(portal_name)
    return RedirectResponse("/admin", status_code=303)


@router.post("/users")
def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
):
    require_admin(request)
    if role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    try:
        create_user(username.strip(), hash_password(password), role)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{username}/disable")
def deactivate_user(request: Request, username: str):
    require_admin(request)
    if not disable_user(username):
        raise HTTPException(status_code=400, detail="User cannot be disabled")
    return RedirectResponse("/admin", status_code=303)
