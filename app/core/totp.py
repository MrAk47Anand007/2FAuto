import time
import pyotp

from app.core.config import settings


def _totp(secret: str, period: int = 30) -> pyotp.TOTP:
    return pyotp.TOTP(secret, interval=period)


def get_otp() -> dict:
    """Return the current OTP code and how many seconds remain in this window."""
    if not settings.OTP_SECRET:
        raise ValueError("Legacy OTP_SECRET is not configured")
    return get_otp_for_secret(settings.OTP_SECRET)


def get_otp_for_secret(secret: str, period: int = 30) -> dict:
    """Return the current OTP code for the supplied TOTP secret."""
    totp = _totp(secret, period)
    code = totp.now()
    now = int(time.time())
    valid_for_seconds = period - (now % period)
    return {
        "otp": code,
        "valid_for_seconds": valid_for_seconds,
        "period": period,
        "timestamp": now,
    }


def verify_otp(code: str) -> bool:
    """Verify a TOTP code, accepting ±1 window (90s tolerance) for clock skew."""
    if not settings.OTP_SECRET:
        return False
    return verify_otp_for_secret(settings.OTP_SECRET, code)


def verify_otp_for_secret(secret: str, code: str, period: int = 30) -> bool:
    """Verify a TOTP code for a supplied secret, accepting +/-1 window."""
    totp = _totp(secret, period)
    return totp.verify(code, valid_window=1)
