import hashlib
import hmac
import secrets
import time
from typing import Any

import bcrypt
from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.database import (
    clear_login_throttle,
    create_session_record,
    get_active_session,
    get_user_by_id,
    is_login_throttled,
    mark_session_step_up,
    record_login_failure,
    reserve_step_up_attempt,
    revoke_session,
    touch_session,
)

SESSION_COOKIE_NAME = "otp_session"
SESSION_ABSOLUTE_MAX_AGE_SECONDS = 8 * 60 * 60
STEP_UP_FRESHNESS_SECONDS = 5 * 60


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session_cookie(user_id: int, role: str | None = None) -> str:
    """Create an opaque cookie and persist only its verifier."""
    del role  # Kept in the signature for callers from the signed-cookie version.
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + min(
        SESSION_ABSOLUTE_MAX_AGE_SECONDS,
        settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
    )
    create_session_record(_token_hash(token), user_id, now, expires_at)
    return token


def read_session_cookie(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return get_active_session(_token_hash(value), int(time.time()))


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    session = read_session_cookie(token)
    if session is None:
        return None

    request.state.session = session
    # Background dashboard polling must not extend the idle timeout forever.
    if request.url.path != "/api/ui/portals":
        touch_session(session["session_id"], int(time.time()))
    return get_user_by_id(int(session["user_id"]))


def current_session(request: Request) -> dict | None:
    session = getattr(request.state, "session", None)
    if session is not None:
        return session
    current_user(request)
    return getattr(request.state, "session", None)


def csrf_token_for_request(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token or current_session(request) is None:
        return None
    return hmac.new(
        settings.SESSION_SECRET.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _check_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    expected = f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"
    allowed_origins = {expected.rstrip("/")}
    if settings.APP_ENV != "production":
        # Local browsers may resolve the same server as either loopback name.
        port = request.headers.get("host", request.url.netloc).rsplit(":", 1)[-1]
        allowed_origins.update({f"http://localhost:{port}", f"http://127.0.0.1:{port}"})
    if not any(hmac.compare_digest(origin.rstrip("/"), allowed) for allowed in allowed_origins):
        raise HTTPException(status_code=403, detail="Origin is not allowed")


async def csrf_protect(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    _check_same_origin(request)
    if request.url.path == "/login":
        return
    expected = csrf_token_for_request(request)
    if expected is None:
        raise HTTPException(status_code=401, detail="Login required")
    supplied = request.headers.get("x-csrf-token")
    if supplied is None:
        form = await request.form()
        supplied_value = form.get("csrf_token")
        supplied = str(supplied_value) if supplied_value is not None else None
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def require_user(request: Request) -> dict:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def complete_step_up(request: Request) -> None:
    session = current_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Login required")
    mark_session_step_up(session["session_id"], int(time.time()))
    session["step_up_at"] = int(time.time())


def verify_step_up_password(user: dict, password: str) -> bool:
    # Share the budget across both endpoints, sessions and source IPs.
    key = _token_hash(f"step-up:{user['id']}")
    if not reserve_step_up_attempt(key, int(time.time())):
        raise HTTPException(status_code=429, detail="Step-up temporarily throttled",
                            headers={"Retry-After": "30"})
    if not verify_password(password, user["password_hash"]):
        return False
    clear_login_throttle(key)
    return True


def require_recent_step_up(request: Request) -> dict:
    user = require_user(request)
    session = current_session(request)
    now = int(time.time())
    if (
        session is None
        or session.get("step_up_at") is None
        or now - int(session["step_up_at"]) > STEP_UP_FRESHNESS_SECONDS
    ):
        raise HTTPException(status_code=428, detail="Recent step-up authentication required")
    return user


def revoke_current_session(request: Request) -> None:
    session = current_session(request)
    if session is not None:
        revoke_session(session["session_id"])


def login_throttle_key(request: Request, username: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    material = f"{client_host}\x00{username.strip().casefold()}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def login_is_throttled(key_hash: str) -> bool:
    return is_login_throttled(key_hash, int(time.time()))


def note_login_failure(key_hash: str) -> None:
    record_login_failure(key_hash, int(time.time()))


def clear_login_failures(key_hash: str) -> None:
    clear_login_throttle(key_hash)
