import re
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.database import (
    create_automation_client,
    create_client_portal_grant,
    get_automation_client,
    get_portal_by_name,
    list_automation_clients,
    list_api_credentials,
    revoke_api_credential,
    revoke_automation_client,
)
from app.core.security import csrf_protect, require_admin, require_recent_step_up
from app.middleware.auth import require_client
from app.services.audit import audit_event
from app.services.clients import issue_client_token
from app.services.otp import PortalNotFound, get_portal_otp_for_client

router = APIRouter(prefix="/api/v1", tags=["Automation clients"])
CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$")


class ClientCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    environment: str = Field(default="production", min_length=1, max_length=32)
    expires_in_days: int = Field(default=90, ge=0, le=3650)


class CredentialRequest(BaseModel):
    expires_in_days: int = Field(default=90, ge=1, le=3650)


class ClientGrantRequest(BaseModel):
    expires_in_days: int = Field(default=30, ge=0, le=3650)


@router.get("/clients")
def clients(request: Request) -> dict:
    require_admin(request)
    return {"clients": list_automation_clients()}


@router.post(
    "/clients",
    dependencies=[Depends(csrf_protect), Depends(require_recent_step_up)],
)
def create_client(request: Request, body: ClientCreateRequest) -> dict:
    admin = require_admin(request)
    if not CLIENT_NAME_RE.fullmatch(body.name):
        raise HTTPException(status_code=400, detail="Invalid client name")
    expires_at = (
        None
        if body.expires_in_days == 0
        else int(time.time()) + body.expires_in_days * 86400
    )
    try:
        client_id = create_automation_client(
            body.name, admin["id"], body.environment, expires_at
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Client name already exists") from exc
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="client.create",
        target_type="client",
        target_id=str(client_id),
        result="success",
        metadata={"client_id": client_id},
    )
    return {"client_id": client_id, "name": body.name}


@router.post(
    "/clients/{client_id}/credentials",
    dependencies=[Depends(csrf_protect), Depends(require_recent_step_up)],
)
def create_credential(
    request: Request,
    client_id: int,
    body: CredentialRequest,
) -> dict:
    admin = require_admin(request)
    client = get_automation_client(client_id)
    if client is None or client["status"] != "active":
        raise HTTPException(status_code=404, detail="Active client not found")
    expires_at = int(time.time()) + body.expires_in_days * 86400
    token = issue_client_token(client_id, expires_at)
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="credential.create",
        target_type="client",
        target_id=str(client_id),
        result="success",
        metadata={"client_id": client_id},
    )
    return {
        "client_id": client_id,
        "credential": token,
        "warning": "Store this credential now; it will not be shown again.",
    }


@router.get("/clients/{client_id}/credentials")
def client_credentials(request: Request, client_id: int) -> dict:
    require_admin(request)
    client = get_automation_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"client_id": client_id, "credentials": list_api_credentials(client_id)}


@router.post(
    "/clients/{client_id}/credentials/{credential_id}/revoke",
    dependencies=[Depends(csrf_protect), Depends(require_recent_step_up)],
)
def revoke_credential(request: Request, client_id: int, credential_id: int) -> dict:
    admin = require_admin(request)
    if not revoke_api_credential(credential_id, client_id):
        raise HTTPException(status_code=404, detail="Active credential not found")
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="credential.revoke",
        target_type="client",
        target_id=str(client_id),
        result="success",
        metadata={"client_id": client_id},
    )
    return {"revoked": True, "client_id": client_id, "credential_id": credential_id}


@router.post(
    "/clients/{client_id}/grants/{portal_name}",
    dependencies=[Depends(csrf_protect), Depends(require_recent_step_up)],
)
def grant_client_portal(
    request: Request,
    client_id: int,
    portal_name: str,
    body: ClientGrantRequest,
) -> dict:
    admin = require_admin(request)
    client = get_automation_client(client_id)
    portal = get_portal_by_name(portal_name)
    if client is None or client["status"] != "active":
        raise HTTPException(status_code=404, detail="Active client not found")
    if portal is None or not portal["is_active"]:
        raise HTTPException(status_code=404, detail="Active portal not found")
    expires_at = (
        None
        if body.expires_in_days == 0
        else int(time.time()) + body.expires_in_days * 86400
    )
    create_client_portal_grant(client_id, portal["id"], admin["id"], expires_at)
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="client.grant.create",
        target_type="client",
        target_id=str(client_id),
        result="success",
        metadata={"client_id": client_id, "portal_name": portal_name},
    )
    return {"granted": True, "client_id": client_id, "portal_name": portal_name}


@router.post(
    "/clients/{client_id}/revoke",
    dependencies=[Depends(csrf_protect), Depends(require_recent_step_up)],
)
def revoke_client(request: Request, client_id: int) -> dict:
    admin = require_admin(request)
    if not revoke_automation_client(client_id):
        raise HTTPException(status_code=404, detail="Active client not found")
    audit_event(
        actor_user_id=admin["id"],
        actor_kind="user",
        action="client.revoke",
        target_type="client",
        target_id=str(client_id),
        result="success",
        metadata={"client_id": client_id},
    )
    return {"revoked": True, "client_id": client_id}


@router.post("/portals/{portal_name}/otp")
def client_otp(request: Request, portal_name: str, client: dict = Depends(require_client)) -> dict:
    try:
        return get_portal_otp_for_client(client, portal_name)
    except PortalNotFound as exc:
        raise HTTPException(status_code=404, detail="OTP portal not found") from exc
