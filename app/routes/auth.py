from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import get_user_by_username, list_user_sessions, revoke_session
from app.core.security import (
    SESSION_COOKIE_NAME,
    create_session_cookie,
    complete_step_up,
    current_user,
    current_session,
    csrf_protect,
    clear_login_failures,
    login_is_throttled,
    login_throttle_key,
    note_login_failure,
    require_user,
    revoke_current_session,
    verify_password,
)
from app.services.audit import audit_event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def root(request: Request):
    if current_user(request):
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", dependencies=[Depends(csrf_protect)])
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    throttle_key = login_throttle_key(request, username)
    if login_is_throttled(throttle_key):
        audit_event(
            actor_user_id=None,
            actor_kind="anonymous",
            action="login",
            target_type="username",
            target_id=username.strip(),
            result="denied",
            reason="throttled",
        )
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password"},
            status_code=401,
        )

    user = get_user_by_username(username)
    if user is None or not verify_password(password, user["password_hash"]):
        note_login_failure(throttle_key)
        audit_event(
            actor_user_id=None,
            actor_kind="anonymous",
            action="login",
            target_type="username",
            target_id=username.strip(),
            result="denied",
            reason="invalid_credentials",
        )
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password"},
            status_code=401,
        )

    clear_login_failures(throttle_key)
    audit_event(
        actor_user_id=user["id"],
        actor_kind="user",
        action="login",
        target_type="user",
        target_id=str(user["id"]),
        result="success",
    )
    target = "/admin" if user["role"] == "admin" else "/dashboard"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_cookie(user["id"], user["role"]),
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        path="/",
    )
    return response


@router.post("/logout", dependencies=[Depends(csrf_protect)])
def logout(request: Request):
    user = current_user(request)
    revoke_current_session(request)
    if user is not None:
        audit_event(
            actor_user_id=user["id"],
            actor_kind="user",
            action="logout",
            target_type="session",
            target_id=str(current_session(request)["session_id"]),
            result="success",
        )
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/api/v1/me/step-up", dependencies=[Depends(csrf_protect)])
def step_up(request: Request, password: str = Form(...)) -> dict:
    user = require_user(request)
    if not verify_password(password, user["password_hash"]):
        audit_event(
            actor_user_id=user["id"],
            actor_kind="user",
            action="step_up",
            target_type="session",
            target_id=str(current_session(request)["session_id"]),
            result="denied",
            reason="invalid_password",
        )
        raise HTTPException(status_code=403, detail="Step-up authentication failed")
    complete_step_up(request)
    audit_event(
        actor_user_id=user["id"],
        actor_kind="user",
        action="step_up",
        target_type="session",
        target_id=str(current_session(request)["session_id"]),
        result="success",
    )
    return {"step_up": True, "valid_for_seconds": 300}


@router.get("/api/v1/me/sessions")
def my_sessions(request: Request) -> dict:
    user = require_user(request)
    active = current_session(request)
    active_id = active["session_id"] if active else None
    return {
        "sessions": [
            {
                **session,
                "current": session["id"] == active_id,
            }
            for session in list_user_sessions(user["id"])
        ]
    }


@router.delete("/api/v1/me/sessions/{session_id}", dependencies=[Depends(csrf_protect)])
def revoke_my_session(request: Request, session_id: int) -> dict:
    user = require_user(request)
    if not revoke_session(session_id, user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"revoked": True, "session_id": session_id}
