"""Shared HTTP security headers for API and legacy HTML responses."""

from app.core.config import settings


def build_content_security_policy(*, strict: bool = True) -> str:
    """
    Build a CSP suitable for the FastAPI/Jinja surface.

    `strict=True` is intended for production; development keeps Vite-friendly
    allowances when callers pass strict=False.
    """
    if strict and settings.APP_ENV == "production":
        script_src = "'self'"
        connect_src = "'self'"
    else:
        script_src = "'self' 'unsafe-inline' 'unsafe-eval'"
        connect_src = "'self' ws: wss: http://localhost:* http://127.0.0.1:*"

    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        f"connect-src {connect_src}; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'"
    )


def apply_security_headers(headers: dict[str, str]) -> None:
    """Mutate a header mapping with baseline protections."""
    policy = build_content_security_policy()
    header_name = (
        "Content-Security-Policy-Report-Only"
        if settings.CONTENT_SECURITY_POLICY_REPORT_ONLY
        else "Content-Security-Policy"
    )
    headers.setdefault(header_name, policy)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "same-origin")
    headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=()",
    )
