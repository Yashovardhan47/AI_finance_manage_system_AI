from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    detail: dict | None = None,
) -> AuditLog:
    event = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    )
    db.add(event)
    return event

