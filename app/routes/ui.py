from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.database import list_active_otp_entries_for_user
from app.core.security import csrf_protect, csrf_token_for_request, require_user
from app.services.otp import PortalNotFound, get_portal_otp_for_user

router = APIRouter(tags=["UI"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = require_user(request)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "csrf_token": csrf_token_for_request(request)},
    )


@router.get("/api/ui/portals")
def dashboard_portals(request: Request) -> dict:
    user = require_user(request)
    return {
        "portals": [
            {
                "portal_name": portal["portal_name"],
                "display_name": portal["display_name"],
                "period": portal["period"],
            }
            for portal in list_active_otp_entries_for_user(user["id"])
        ]
    }


@router.post("/api/ui/portals/{portal_name}/otp", dependencies=[Depends(csrf_protect)])
def reveal_dashboard_otp(request: Request, portal_name: str) -> dict:
    user = require_user(request)
    try:
        return get_portal_otp_for_user(user["id"], portal_name)
    except PortalNotFound as exc:
        raise HTTPException(status_code=404, detail="OTP portal not found") from exc


@router.get("/api/ui/otps")
def retired_dashboard_otps(request: Request) -> dict:
    require_user(request)
    raise HTTPException(
        status_code=410,
        detail="Bulk OTP retrieval is retired; reveal a portal explicitly",
    )
