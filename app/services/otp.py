from app.core import totp as totp_core
from app.core.database import (
    get_client_portal_entry,
    get_otp_entry_by_portal,
    get_otp_entry_by_portal_for_user,
    list_active_otp_entries_for_user,
)
from app.core.secrets import decrypt_secret
from app.core.totp import get_otp_for_secret
from app.services.audit import audit_event


class PortalNotFound(LookupError):
    """Raised when an active portal is unavailable."""


def _issue_otp(
    entry: dict,
    *,
    actor_user_id: int | None,
    actor_kind: str,
    audit_metadata: dict[str, str | int | bool] | None = None,
) -> dict:
    secret = decrypt_secret(
        entry["secret_ciphertext"],
        entry["secret_nonce"],
        entry["portal_name"],
        entry["encryption_version"],
        entry["key_version"],
    )
    result = get_otp_for_secret(secret, entry["period"])
    audit_event(
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
        action="otp.release",
        target_type="portal",
        target_id=entry["portal_name"],
        result="success",
        metadata={
            "period": entry["period"],
            "portal_name": entry["portal_name"],
            **(audit_metadata or {}),
        },
    )
    result.update(
        {
            "portal_name": entry["portal_name"],
            "display_name": entry["display_name"],
        }
    )
    return result


def get_portal_otp(portal_name: str) -> dict:
    entry = get_otp_entry_by_portal(portal_name)
    if entry is None:
        raise PortalNotFound
    return _issue_otp(
        entry,
        actor_user_id=None,
        actor_kind="legacy_api_key",
    )


def get_portal_otp_for_user(user_id: int, portal_name: str) -> dict:
    entry = get_otp_entry_by_portal_for_user(portal_name, user_id)
    if entry is None:
        audit_event(
            actor_user_id=user_id,
            actor_kind="user",
            action="otp.release",
            target_type="portal",
            target_id=portal_name,
            result="denied",
            reason="portal_not_granted_or_inactive",
        )
        raise PortalNotFound
    return _issue_otp(
        entry,
        actor_user_id=user_id,
        actor_kind="user",
    )


def list_active_otps(user_id: int) -> list[dict]:
    results = []
    for metadata in list_active_otp_entries_for_user(user_id):
        entry = get_otp_entry_by_portal_for_user(metadata["portal_name"], user_id)
        if entry is not None:
            results.append(
                _issue_otp(
                    entry,
                    actor_user_id=user_id,
                    actor_kind="user",
                )
            )
    return results


def get_portal_otp_for_client(client: dict, portal_name: str) -> dict:
    entry = get_client_portal_entry(client["client_id"], portal_name)
    if entry is None:
        audit_event(
            actor_user_id=client["owner_user_id"],
            actor_kind="client",
            action="otp.release",
            target_type="portal",
            target_id=portal_name,
            result="denied",
            reason="portal_not_granted_or_inactive",
            metadata={"client_id": client["client_id"]},
        )
        raise PortalNotFound
    return _issue_otp(
        entry,
        actor_user_id=client["owner_user_id"],
        actor_kind="client",
        audit_metadata={"client_id": client["client_id"]},
    )


def issue_legacy_otp() -> dict:
    result = totp_core.get_otp()
    audit_event(
        actor_user_id=None,
        actor_kind="legacy_api_key",
        action="otp.release",
        target_type="legacy_otp",
        target_id="OTP_SECRET",
        result="success",
        metadata={"period": result["period"]},
    )
    return result
