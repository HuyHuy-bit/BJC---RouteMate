import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_pii_access(
    db: Session,
    actor_user_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
) -> None:
    """
    Call this whenever a route decrypts and returns raw customer PII
    (phone number, address text) to a caller. Separate commit from the
    caller's main transaction isn't required — this just adds a row that
    gets committed along with whatever else the request does.
    """
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
        )
    )
