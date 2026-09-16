from app.core.database import record_audit_event

SAFE_METADATA_KEYS = {
    "period",
    "portal_name",
    "permission",
    "client_id",
    "user_id",
    "session_id",
    "status_code",
}


def audit_event(
    *,
    actor_user_id: int | None,
    actor_kind: str,
    action: str,
    target_type: str,
    target_id: str | None,
    result: str,
    reason: str | None = None,
    metadata: dict[str, str | int | bool] | None = None,
) -> str:
    safe_metadata = {
        key: value
        for key, value in (metadata or {}).items()
        if key in SAFE_METADATA_KEYS
    }
    return record_audit_event(
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result=result,
        reason=reason,
        metadata=safe_metadata,
    )
