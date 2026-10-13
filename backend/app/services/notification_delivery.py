from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.billing_models import BillingNotification, NotificationPreference, NotificationStatus
from app.core.config import Settings, get_settings
from app.monitoring import NOTIFICATION_ATTEMPTS
from app.services.billing_utils import as_utc, utcnow
from app.services.notification_adapters import adapter_for
from app.services.realtime import publish_billing_event


def claim_notifications(
    db: Session,
    *,
    now: datetime | None = None,
    batch_size: int | None = None,
    settings: Settings | None = None,
) -> list[int]:
    """Atomically lease due outbox rows across concurrent PostgreSQL workers."""
    settings = settings or get_settings()
    claimed_at = as_utc(now or utcnow())
    rows = list(
        db.scalars(
            notification_claim_statement(
                now=claimed_at,
                batch_size=batch_size or settings.notification_claim_batch_size,
            )
        )
    )
    for row in rows:
        row.delivery_status = "processing"
        row.attempt_count += 1
        row.last_attempt_at = claimed_at
        row.lease_expires_at = claimed_at + timedelta(seconds=settings.notification_lease_seconds)
    db.commit()
    return [row.id for row in rows]


def notification_claim_statement(*, now: datetime, batch_size: int):
    return (
        select(BillingNotification)
        .where(
            BillingNotification.delivery_status.in_(["queued", "retry_scheduled", "processing"]),
            BillingNotification.next_attempt_at <= now,
            or_(
                BillingNotification.lease_expires_at.is_(None),
                BillingNotification.lease_expires_at <= now,
            ),
        )
        .order_by(BillingNotification.next_attempt_at, BillingNotification.id)
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )


def deliver_notification_batch(
    db: Session,
    *,
    now: datetime | None = None,
    batch_size: int | None = None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    attempted_at = as_utc(now or utcnow())
    ids = claim_notifications(db, now=attempted_at, batch_size=batch_size, settings=settings)
    result = {"claimed": len(ids), "sent": 0, "retried": 0, "dead_lettered": 0, "deferred": 0}
    for notification_id in ids:
        item = db.get(BillingNotification, notification_id)
        if not item or item.delivery_status != "processing":
            continue
        quiet_until = _quiet_hours_end(db, item, attempted_at)
        if quiet_until:
            item.delivery_status = "queued"
            item.next_attempt_at = quiet_until
            item.lease_expires_at = None
            item.attempt_count = max(0, item.attempt_count - 1)
            result["deferred"] += 1
            db.commit()
            continue
        try:
            delivery = adapter_for(item, settings).send(item)
        except Exception as exc:  # provider SDKs expose heterogeneous errors
            _record_failure(db, item, exc, attempted_at, settings)
            if item.delivery_status == "failed":
                result["dead_lettered"] += 1
            else:
                result["retried"] += 1
            NOTIFICATION_ATTEMPTS.labels(item.channel, item.provider, "failed").inc()
            db.commit()
            continue

        item.provider = delivery.provider
        item.provider_message_id = delivery.message_id
        item.provider_response = delivery.response
        item.status = NotificationStatus.sent
        item.delivery_status = "sent"
        item.failure_reason = None
        item.sent_at = attempted_at
        item.lease_expires_at = None
        publish_billing_event(
            db,
            owner_user_id=item.owner_user_id,
            event_type="notification.sent",
            entity_type="billing_notification",
            entity_id=item.id,
            payload={"channel": item.channel, "provider": item.provider, "delivery_status": item.delivery_status},
        )
        NOTIFICATION_ATTEMPTS.labels(item.channel, item.provider, "sent").inc()
        result["sent"] += 1
        db.commit()
    return result


def _record_failure(
    db: Session,
    item: BillingNotification,
    error: Exception,
    now: datetime,
    settings: Settings,
) -> None:
    item.failure_reason = str(error)[:2000]
    item.provider_response = {"error_type": type(error).__name__}
    item.lease_expires_at = None
    if item.attempt_count >= item.max_attempts:
        item.delivery_status = "failed"
        item.status = NotificationStatus.failed
        item.failed_at = now
        item.dead_lettered_at = now
        from app.services.payment_incidents import open_payment_incident

        open_payment_incident(
            db,
            owner_user_id=item.owner_user_id,
            customer_id=item.customer_id,
            invoice_id=item.invoice_id,
            incident_type="notification_delivery_exhausted",
            severity="warning",
            summary=f"{item.channel.title()} delivery exhausted after {item.attempt_count} attempts",
            details={"notification_id": item.id, "event_type": item.event_type, "error": item.failure_reason},
            dedupe_key=f"notification:{item.id}:delivery_exhausted",
        )
        event_type = "notification.failed"
    else:
        seconds = min(
            settings.notification_backoff_cap_seconds,
            settings.notification_backoff_base_seconds * (2 ** max(0, item.attempt_count - 1)),
        )
        item.delivery_status = "retry_scheduled"
        item.next_attempt_at = now + timedelta(seconds=seconds)
        event_type = "notification.retry_scheduled"
    publish_billing_event(
        db,
        owner_user_id=item.owner_user_id,
        event_type=event_type,
        entity_type="billing_notification",
        entity_id=item.id,
        payload={
            "channel": item.channel,
            "attempt_count": item.attempt_count,
            "max_attempts": item.max_attempts,
            "next_attempt_at": item.next_attempt_at.isoformat() if item.delivery_status != "failed" else None,
        },
    )


def _quiet_hours_end(db: Session, item: BillingNotification, now: datetime) -> datetime | None:
    preference = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.owner_user_id == item.owner_user_id,
            NotificationPreference.customer_id == item.customer_id,
        )
    )
    if not preference or not preference.quiet_hours_start or not preference.quiet_hours_end:
        return None
    try:
        timezone = ZoneInfo(preference.timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    local_now = now.astimezone(timezone)
    start_hour, start_minute = map(int, preference.quiet_hours_start.split(":"))
    end_hour, end_minute = map(int, preference.quiet_hours_end.split(":"))
    start = local_now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = local_now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if start <= end:
        active = start <= local_now < end
    else:
        active = local_now >= start or local_now < end
        if local_now >= start:
            end += timedelta(days=1)
    return end.astimezone(ZoneInfo("UTC")) if active else None
