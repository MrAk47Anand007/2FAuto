from typing import Any

import bcrypt
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings
from app.core.database import get_user_by_id

SESSION_COOKIE_NAME = "otp_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.SESSION_SECRET, salt="otp-portal-session")


def create_session_cookie(user_id: int, role: str) -> str:
    return _serializer().dumps({"user_id": user_id, "role": role})


def read_session_cookie(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        return _serializer().loads(value, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


def current_user(request: Request) -> dict | None:
    payload = read_session_cookie(request.cookies.get(SESSION_COOKIE_NAME))
    if payload is None:
        return None
    user = get_user_by_id(int(payload["user_id"]))
    return user


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
