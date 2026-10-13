from sqlalchemy.orm import Session

from app.billing_models import RealtimeBillingEvent


def publish_billing_event(
    db: Session,
    *,
    owner_user_id: int,
    event_type: str,
    entity_type: str,
    entity_id: int | None = None,
    payload: dict | None = None,
) -> RealtimeBillingEvent:
    """Persist an event in the same transaction as the domain change.

    SSE clients read this table by monotonically increasing id, so events are
    durable across API and worker processes and reconnects can resume safely.
    """
    event = RealtimeBillingEvent(
        owner_user_id=owner_user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    db.add(event)
    return event
