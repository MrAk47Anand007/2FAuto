import re
import sqlite3
import time
from urllib.parse import parse_qs, urlparse

import pyotp
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.database import (
    create_otp_entry,
    create_portal_grant,
    create_team,
    create_team_portal_grant,
    create_user,
    delete_otp_entry,
    disable_otp_entry,
    disable_user,
    get_portal_by_name,
    get_user_by_exact_username,
    get_team_by_name,
    add_team_member,
    list_otp_entries,
    list_portal_grants,
    list_users,
    list_teams,
    list_audit_events,
    reactivate_otp_entry,
    reactivate_user,
    revoke_portal_grant,
    remove_team_member,
    revoke_team_portal_grant,
    update_otp_entry_metadata,
)
from app.core.security import (
    csrf_protect,
    csrf_token_for_request,
    complete_step_up,
    hash_password,
    require_admin,
    require_recent_step_up,
    verify_step_up_password,
)
from app.services.audit import audit_event

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(csrf_protect)],
)
templates = Jinja2Templates(directory="app/templates")
PORTAL_NAME_RE = re.compile(r"^[a-z0-9-]{2,64}$")
TEAM_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _.-]{1,63}$")


def _parse_totp_input(raw_value: str, period: int) -> tuple[str, int]:
    """Accept a Base32 secret or strictly parse a local otpauth TOTP URI."""
    value = raw_value.strip()
    if not value.lower().startswith("otpauth://"):
        return value.replace(" ", ""), period

    parsed = urlparse(value)
    if parsed.scheme.lower() != "otpauth" or parsed.netloc.lower() != "totp" or not parsed.path.strip("/"):
        raise HTTPException(status_code=400, detail="Only a valid otpauth TOTP URI is supported")
    query = parse_qs(parsed.query, keep_blank_values=True)
    allowed = {"secret", "issuer", "algorithm", "digits", "period"}
    if set(query) - allowed or "secret" not in query or len(query["secret"]) != 1:
        raise HTTPException(status_code=400, detail="Unsupported or incomplete otpauth URI")
    if query.get("algorithm", ["SHA1"])[0].upper() != "SHA1":
        raise HTTPException(status_code=400, detail="Only SHA1 TOTP URIs are supported")
    if query.get("digits", ["6"])[0] != "6":
        raise HTTPException(status_code=400, detail="Only six-digit TOTP URIs are supported")
    try:
        uri_period = int(query.get("period", [str(period)])[0])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="TOTP URI period must be an integer") from exc
    if uri_period < 10 or uri_period > 120:
        raise HTTPException(status_code=400, detail="TOTP URI period must be between 10 and 120 seconds")
    return query["secret"][0].replace(" ", ""), uri_period


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request):
    admin = require_admin(request)
    portals = [
        {
            **portal,
            "masked_secret": "encrypted at rest",
            "grants": list_portal_grants(portal["id"]),
        }
        for portal in list_otp_entries()
    ]
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": admin,
            "portals": portals,
            "users": list_users(),
            "teams": list_teams(),
            "error": None,
            "csrf_token": csrf_token_for_request(request),
        },
    )


@router.post("/portals", dependencies=[Depends(require_recent_step_up)])
def add_portal(
    request: Request,
    portal_name: str = Form(...),
    display_name: str = Form(...),
    secret: str = Form(...),
    period: int = Form(30),
):
    admin = require_admin(request)
    portal_name = portal_name.strip().lower()
    clean_secret, period = _parse_totp_input(secret, period)

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

    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="portal.create",
        target_type="portal",
        target_id=portal_name,
        result="success",
        metadata={"period": period},
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/step-up")
def admin_step_up(request: Request, password: str = Form(...)):
    admin = require_admin(request)
    if not verify_step_up_password(admin, password):
        audit_event(
            actor_user_id=admin["id"],
            actor_kind="user",
            action="step_up",
            target_type="session",
            target_id=str(request.state.session["session_id"]),
            result="denied",
            reason="invalid_password",
        )
        raise HTTPException(status_code=403, detail="Step-up authentication failed")
    complete_step_up(request)
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="step_up",
        target_type="session",
        target_id=str(request.state.session["session_id"]),
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/portals/{portal_name}/grants", dependencies=[Depends(require_recent_step_up)])
def grant_portal_access(
    request: Request,
    portal_name: str,
    username: str = Form(...),
    expires_in_days: int = Form(30),
):
    admin = require_admin(request)
    if expires_in_days < 0 or expires_in_days > 3650:
        raise HTTPException(status_code=400, detail="Grant expiry must be between 0 and 3650 days")
    portal = get_portal_by_name(portal_name)
    user = get_user_by_exact_username(username)
    if portal is None or not portal["is_active"]:
        raise HTTPException(status_code=404, detail="OTP portal not found")
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=404, detail="Active user not found")
    expires_at = (
        None if expires_in_days == 0 else int(time.time()) + expires_in_days * 86400
    )
    create_portal_grant(
        portal["id"], user["id"], admin["id"], "read", expires_at
    )
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="grant.create",
        target_type="portal",
        target_id=portal_name,
        result="success",
        metadata={"permission": "read", "portal_name": portal_name},
    )
    return RedirectResponse("/admin", status_code=303)


@router.post(
    "/portals/{portal_name}/grants/{username}/revoke",
    dependencies=[Depends(require_recent_step_up)],
)
def revoke_portal_access(request: Request, portal_name: str, username: str):
    admin = require_admin(request)
    portal = get_portal_by_name(portal_name)
    user = get_user_by_exact_username(username)
    if portal is None or user is None:
        raise HTTPException(status_code=404, detail="Portal or user not found")
    revoke_portal_grant(portal["id"], user["id"])
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="grant.revoke",
        target_type="portal",
        target_id=portal_name,
        result="success",
        metadata={"permission": "read", "portal_name": portal_name},
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/teams", dependencies=[Depends(require_recent_step_up)])
def add_team(request: Request, name: str = Form(...)):
    admin = require_admin(request)
    name = name.strip()
    if not TEAM_NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Team name must use letters, numbers, spaces, dots, underscores, or hyphens")
    try:
        team_id = create_team(name, admin["id"])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Team name already exists") from exc
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="team.create",
        target_type="team",
        target_id=str(team_id),
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/teams/{team_name}/members", dependencies=[Depends(require_recent_step_up)])
def add_member_to_team(request: Request, team_name: str, username: str = Form(...)):
    admin = require_admin(request)
    team = get_team_by_name(team_name)
    user = get_user_by_exact_username(username)
    if team is None or not team["is_active"]:
        raise HTTPException(status_code=404, detail="Active team not found")
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=404, detail="Active user not found")
    add_team_member(team["id"], user["id"])
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="team.member.add",
        target_type="team",
        target_id=team_name,
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post(
    "/teams/{team_name}/grants/{portal_name}",
    dependencies=[Depends(require_recent_step_up)],
)
def grant_team_portal(
    request: Request,
    team_name: str,
    portal_name: str,
    expires_in_days: int = Form(30),
):
    admin = require_admin(request)
    team = get_team_by_name(team_name)
    portal = get_portal_by_name(portal_name)
    if team is None or not team["is_active"]:
        raise HTTPException(status_code=404, detail="Active team not found")
    if portal is None or not portal["is_active"]:
        raise HTTPException(status_code=404, detail="Active portal not found")
    if expires_in_days < 0 or expires_in_days > 3650:
        raise HTTPException(status_code=400, detail="Grant expiry must be between 0 and 3650 days")
    expires_at = None if expires_in_days == 0 else int(time.time()) + expires_in_days * 86400
    create_team_portal_grant(team["id"], portal["id"], admin["id"], expires_at)
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="team.grant.create",
        target_type="team",
        target_id=team_name,
        result="success",
        metadata={"portal_name": portal_name, "permission": "read"},
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/teams/{team_name}/members/remove", dependencies=[Depends(require_recent_step_up)])
def remove_member_from_team(request: Request, team_name: str, username: str = Form(...)):
    admin = require_admin(request)
    team = get_team_by_name(team_name)
    user = get_user_by_exact_username(username)
    if team is None or user is None or not remove_team_member(team["id"], user["id"]):
        raise HTTPException(status_code=404, detail="Active membership not found")
    audit_event(actor_user_id=admin["id"], actor_kind="user",
                action="team.member.remove", target_type="team", target_id=team_name,
                result="success", metadata={"user_id": user["id"]})
    return RedirectResponse("/admin", status_code=303)


@router.post("/teams/{team_name}/grants/{portal_name}/revoke", dependencies=[Depends(require_recent_step_up)])
def revoke_team_access(request: Request, team_name: str, portal_name: str):
    admin = require_admin(request)
    team = get_team_by_name(team_name)
    portal = get_portal_by_name(portal_name)
    if team is None or portal is None or not revoke_team_portal_grant(team["id"], portal["id"]):
        raise HTTPException(status_code=404, detail="Active team grant not found")
    audit_event(actor_user_id=admin["id"], actor_kind="user",
                action="team.grant.revoke", target_type="team", target_id=team_name,
                result="success", metadata={"portal_name": portal_name})
    return RedirectResponse("/admin", status_code=303)


@router.post("/portals/{portal_name}/disable", dependencies=[Depends(require_recent_step_up)])
def disable_portal(request: Request, portal_name: str):
    admin = require_admin(request)
    disable_otp_entry(portal_name)
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="portal.disable",
        target_type="portal",
        target_id=portal_name,
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/portals/{portal_name}/reactivate", dependencies=[Depends(require_recent_step_up)])
def reactivate_portal(request: Request, portal_name: str):
    admin = require_admin(request)
    if not reactivate_otp_entry(portal_name):
        raise HTTPException(status_code=404, detail="Disabled portal not found")
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="portal.reactivate",
        target_type="portal",
        target_id=portal_name,
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/portals/{portal_name}/edit", dependencies=[Depends(require_recent_step_up)])
def edit_portal(
    request: Request,
    portal_name: str,
    display_name: str = Form(...),
    period: int = Form(...),
):
    admin = require_admin(request)
    if period < 10 or period > 120 or not display_name.strip():
        raise HTTPException(status_code=400, detail="Invalid portal metadata")
    if not update_otp_entry_metadata(portal_name, display_name, period):
        raise HTTPException(status_code=404, detail="Portal not found")
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="portal.update",
        target_type="portal",
        target_id=portal_name,
        result="success",
        metadata={"period": period},
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/portals/{portal_name}/delete", dependencies=[Depends(require_recent_step_up)])
def delete_portal(request: Request, portal_name: str):
    admin = require_admin(request)
    delete_otp_entry(portal_name)
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="portal.delete",
        target_type="portal",
        target_id=portal_name,
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/users", dependencies=[Depends(require_recent_step_up)])
def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
):
    admin = require_admin(request)
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
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="user.create",
        target_type="user",
        target_id=username.strip(),
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{username}/disable", dependencies=[Depends(require_recent_step_up)])
def deactivate_user(request: Request, username: str):
    admin = require_admin(request)
    if not disable_user(username):
        raise HTTPException(status_code=400, detail="User cannot be disabled")
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="user.disable",
        target_type="user",
        target_id=username.strip(),
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{username}/reactivate", dependencies=[Depends(require_recent_step_up)])
def reactivate_account(request: Request, username: str):
    admin = require_admin(request)
    if not reactivate_user(username):
        raise HTTPException(status_code=404, detail="Disabled user not found")
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="user.reactivate",
        target_type="user",
        target_id=username.strip(),
        result="success",
    )
    return RedirectResponse("/admin", status_code=303)


@router.get("/api/v1/audit")
def audit_search(request: Request, limit: int = 100) -> dict:
    require_admin(request)
    return {"events": list_audit_events(limit)}
