from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.database import list_active_otp_entries
from app.core.security import require_user
from app.core.totp import get_otp_for_secret

router = APIRouter(tags=["UI"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = require_user(request)
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})


@router.get("/api/ui/otps")
def dashboard_otps(request: Request) -> dict:
    require_user(request)
    otps = []
    for entry in list_active_otp_entries():
        otp = get_otp_for_secret(entry["secret"], entry["period"])
        otps.append(
            {
                "portal_name": entry["portal_name"],
                "display_name": entry["display_name"],
                "otp": otp["otp"],
                "valid_for_seconds": otp["valid_for_seconds"],
                "period": otp["period"],
                "timestamp": otp["timestamp"],
            }
        )
    return {"otps": otps}
