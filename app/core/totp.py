import time
import pyotp

from app.core.config import settings


def _totp() -> pyotp.TOTP:
    return pyotp.TOTP(settings.OTP_SECRET)


def get_otp() -> dict:
    """Return the current OTP code and how many seconds remain in this window."""
    totp = _totp()
    code = totp.now()
    now = int(time.time())
    # TOTP window is 30 seconds; time_remaining = 30 - (now % 30)
    valid_for_seconds = 30 - (now % 30)
    return {
        "otp": code,
        "valid_for_seconds": valid_for_seconds,
        "timestamp": now,
    }


def verify_otp(code: str) -> bool:
    """Verify a TOTP code, accepting ±1 window (90s tolerance) for clock skew."""
    totp = _totp()
    return totp.verify(code, valid_window=1)
