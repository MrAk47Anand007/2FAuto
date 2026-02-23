import hmac
import hashlib
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.core.config import settings

# Maximum age (seconds) of a signed request before it is rejected
SIGNATURE_MAX_AGE_SECONDS = 30


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """Dependency: validate the X-API-Key header using constant-time comparison."""
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-Key header is required")
    if not hmac.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key


def require_hmac_signature(
    api_key: Annotated[str, Depends(require_api_key)],
    x_timestamp: Annotated[str | None, Header()] = None,
    x_signature: Annotated[str | None, Header()] = None,
) -> None:
    """
    Dependency: validate HMAC-SHA256 request signature.

    Expected client computation:
        signature = hmac.new(API_KEY.encode(), timestamp.encode(), hashlib.sha256).hexdigest()

    Headers required:
        X-Timestamp  – Unix timestamp (integer string) when the request was made
        X-Signature  – HMAC-SHA256 hex digest of the timestamp using the API key as the secret
    """
    if x_timestamp is None:
        raise HTTPException(status_code=401, detail="X-Timestamp header is required")
    if x_signature is None:
        raise HTTPException(status_code=401, detail="X-Signature header is required")

    # Validate timestamp format
    try:
        request_time = int(x_timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Timestamp must be a unix integer")

    # Replay-attack prevention: reject stale requests
    age = abs(int(time.time()) - request_time)
    if age > SIGNATURE_MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Request timestamp is expired")

    # Compute expected signature
    expected = hmac.new(
        api_key.encode(),
        x_timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(x_signature, expected):
        raise HTTPException(status_code=403, detail="Invalid request signature")
