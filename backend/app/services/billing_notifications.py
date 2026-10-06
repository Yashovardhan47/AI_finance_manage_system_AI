from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing_models import (
    BillingCustomer,
    BillingInvoice,
    BillingNotification,
    NotificationPreference,
)
from app.core.config import get_settings
from app.services.realtime import publish_billing_event


def queue_billing_notification(
    db: Session,
    *,
    owner_user_id: int,
    customer: BillingCustomer,
    event_type: str,
    invoice: BillingInvoice | None = None,
    payload: dict | None = None,
    channels_override: list[str] | None = None,
    escalation_level: int = 0,
    idempotency_key: str | None = None,
) -> BillingNotification | None:
    """Write channel-specific messages to the transactional outbox.

    The caller's domain transaction owns the commit. This ensures a payment
    state change and the notifications that describe it are atomic.
    """
    settings = get_settings()
    preference = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.owner_user_id == owner_user_id,
            NotificationPreference.customer_id == customer.id,
        )
    )
    if preference and "*" not in preference.event_types and event_type not in preference.event_types:
        return None

    recipients = _recipients(customer, preference)
    channel_policy = {
        "email": preference.email_enabled if preference else True,
        "sms": preference.sms_enabled if preference else False,
        "push": preference.push_enabled if preference else False,
    }
    requested_channels = channels_override or list(channel_policy)
    enabled = [channel for channel in requested_channels if channel_policy.get(channel, False)]
    created: list[BillingNotification] = []
    event_payload = payload or {}
    seed = idempotency_key or uuid4().hex
    for channel in dict.fromkeys(enabled):
        recipient = recipients.get(channel)
        if not recipient:
            continue
        digest = hashlib.sha256(
            json.dumps(
                [seed, event_type, invoice.id if invoice else None, channel, event_payload],
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:40]
        dedupe_key = f"{event_type}:{digest}"
        existing = db.scalar(
            select(BillingNotification).where(
                BillingNotification.owner_user_id == owner_user_id,
                BillingNotification.dedupe_key == dedupe_key,
            )
        )
        if existing:
            created.append(existing)
            continue
        notification = BillingNotification(
            owner_user_id=owner_user_id,
            customer_id=customer.id,
            invoice_id=invoice.id if invoice else None,
            event_type=event_type,
            recipient=recipient,
            channel=channel,
            payload=event_payload,
            max_attempts=preference.max_delivery_attempts if preference else settings.notification_max_attempts,
            provider=_configured_provider(channel),
            dedupe_key=dedupe_key,
            escalation_level=escalation_level,
        )
        db.add(notification)
        created.append(notification)
    if created:
        db.flush()
        publish_billing_event(
            db,
            owner_user_id=owner_user_id,
            event_type="notification.queued",
            entity_type="billing_notification",
            entity_id=created[0].id,
            payload={"event_type": event_type, "channels": [item.channel for item in created]},
        )
    return created[0] if created else None


def _recipients(customer: BillingCustomer, preference: NotificationPreference | None) -> dict[str, str | None]:
    return {
        "email": preference.email_address if preference and preference.email_address else customer.email,
        "sms": preference.phone_number if preference else None,
        "push": preference.push_token if preference else None,
    }


def _configured_provider(channel: str) -> str:
    settings = get_settings()
    return {
        "email": settings.email_provider,
        "sms": settings.sms_provider,
        "push": settings.push_provider,
    }.get(channel, "sandbox")
