import hashlib
import hmac
import secrets
import time

from app.core.database import (
    create_api_credential,
    get_client_credential,
    touch_api_credential,
)

TOKEN_PREFIX = "otp_"


def _verifier(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def issue_client_token(
    client_id: int,
    expires_at: int | None,
) -> str:
    lookup_id = secrets.token_urlsafe(12)
    secret = secrets.token_urlsafe(32)
    create_api_credential(client_id, lookup_id, _verifier(secret), expires_at)
    return f"{TOKEN_PREFIX}{lookup_id}.{secret}"


def authenticate_client_token(token: str | None) -> dict | None:
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    lookup_and_secret = token[len(TOKEN_PREFIX) :]
    lookup_id, separator, secret = lookup_and_secret.partition(".")
    if not separator or not lookup_id or not secret:
        return None
    record = get_client_credential(lookup_id, int(time.time()))
    if record is None:
        return None
    if not hmac.compare_digest(_verifier(secret), record["verifier_hash"]):
        return None
    touch_api_credential(record["credential_id"], int(time.time()))
    return record
