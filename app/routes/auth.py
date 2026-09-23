import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import get_user_by_username, list_user_sessions, revoke_session
from app.core.security import (
    SESSION_COOKIE_NAME,
    create_session_cookie,
    complete_step_up,
    current_user,
    current_session,
    csrf_token_for_request,
    csrf_protect,
    clear_login_failures,
    login_is_throttled,
    login_throttle_key,
    note_login_failure,
    require_user,
    revoke_current_session,
    verify_password,
    verify_step_up_password,
)
from app.services.audit import audit_event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


def _login_user(request: Request, username: str, password: str) -> dict | None:
    """Authenticate once so HTML and SPA login paths have identical controls."""
    throttle_key = login_throttle_key(request, username)
    if login_is_throttled(throttle_key):
        audit_event(
            actor_user_id=None, actor_kind="anonymous", action="login",
            target_type="username", target_id=username.strip(), result="denied", reason="throttled",
        )
        return None
    user = get_user_by_username(username)
    if user is None or not verify_password(password, user["password_hash"]):
        note_login_failure(throttle_key)
        audit_event(
            actor_user_id=None, actor_kind="anonymous", action="login",
            target_type="username", target_id=username.strip(), result="denied", reason="invalid_credentials",
        )
        return None
    clear_login_failures(throttle_key)
    audit_event(
        actor_user_id=user["id"], actor_kind="user", action="login",
        target_type="user", target_id=str(user["id"]), result="success",
    )
    return user


def _login_response(
    user: dict,
    response: JSONResponse | RedirectResponse,
    session_token: str | None = None,
) -> JSONResponse | RedirectResponse:
    token = session_token or create_session_cookie(user["id"], user["role"])
    response.set_cookie(
        SESSION_COOKIE_NAME, token,
        httponly=True, samesite="lax", secure=settings.COOKIE_SECURE,
        max_age=settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS, path="/",
    )
    return response


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
    user = _login_user(request, username, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password"},
            status_code=401,
        )

    target = "/admin" if user["role"] == "admin" else "/dashboard"
    return _login_response(user, RedirectResponse(target, status_code=303))


@router.post("/api/v1/auth/login", dependencies=[Depends(csrf_protect)])
def api_login(request: Request, body: LoginRequest) -> JSONResponse:
    user = _login_user(request, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    import hashlib
    import hmac
    session_token = create_session_cookie(user["id"], user["role"])
    response = JSONResponse({
        "id": user["id"], "username": user["username"], "role": user["role"],
        "csrf_token": hmac.new(settings.SESSION_SECRET.encode("utf-8"), session_token.encode("utf-8"), hashlib.sha256).hexdigest(),
    })
    return _login_response(user, response, session_token)


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


@router.post("/api/v1/auth/logout", dependencies=[Depends(csrf_protect)])
def api_logout(request: Request) -> JSONResponse:
    user = current_user(request)
    revoke_current_session(request)
    if user is not None:
        audit_event(actor_user_id=user["id"], actor_kind="user", action="logout",
                    target_type="session", target_id=str(current_session(request)["session_id"]), result="success")
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME, secure=settings.COOKIE_SECURE,
                           httponly=True, samesite="lax", path="/")
    return response


@router.get("/api/v1/me")
def me(request: Request) -> dict:
    user = current_user(request, touch_activity=False)
    session = current_session(request, touch_activity=False)
    if user is None or session is None:
        raise HTTPException(status_code=401, detail="Login required")
    step_up_at = session.get("step_up_at")
    return {
        "id": user["id"], "username": user["username"], "role": user["role"],
        "csrf_token": csrf_token_for_request(request, touch_activity=False),
        "session_expires_at": session["expires_at"],
        "step_up_expires_at": int(step_up_at) + 300 if step_up_at else None,
    }


@router.post("/api/v1/me/step-up", dependencies=[Depends(csrf_protect)])
def step_up(request: Request, password: str = Form(...)) -> dict:
    user = require_user(request)
    if not verify_step_up_password(user, password):
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
    now = int(time.time())
    sessions = []
    for session in list_user_sessions(user["id"]):
        if session["revoked_at"] is not None:
            status = "revoked"
        elif (
            session["expires_at"] <= now
            or session["last_active_at"] <= now - settings.SESSION_IDLE_TIMEOUT_SECONDS
        ):
            status = "expired"
        else:
            status = "active"
        sessions.append({**session, "current": session["id"] == active_id, "status": status})
    return {"sessions": sessions}


@router.delete("/api/v1/me/sessions/{session_id}", dependencies=[Depends(csrf_protect)])
def revoke_my_session(request: Request, session_id: int) -> dict:
    user = require_user(request)
    if not revoke_session(session_id, user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"revoked": True, "session_id": session_id}
