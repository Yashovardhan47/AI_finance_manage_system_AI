from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing_models import BillingNotification, NotificationReceipt, NotificationStatus
from app.services.billing_utils import as_utc, utcnow
from app.services.realtime import publish_billing_event


def sign_notification_receipt(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode(), _canonical(payload), hashlib.sha256).hexdigest()


def verify_notification_receipt(payload: dict, signature: str, secret: str) -> bool:
    expected = sign_notification_receipt(payload, secret)
    return hmac.compare_digest(expected, signature)


def process_notification_receipt(
    db: Session,
    *,
    provider: str,
    payload: dict,
) -> dict:
    existing = db.scalar(
        select(NotificationReceipt).where(
            NotificationReceipt.provider == provider,
            NotificationReceipt.event_id == payload["event_id"],
        )
    )
    if existing:
        return {"duplicate": True, "notification_id": existing.notification_id, "status": existing.delivery_status}
    notification = db.scalar(
        select(BillingNotification).where(
            BillingNotification.provider == provider,
            BillingNotification.provider_message_id == payload["provider_message_id"],
        )
    )
    if not notification:
        raise ValueError("No notification matches this provider message id")
    occurred_at = as_utc(payload.get("occurred_at") or utcnow())
    receipt_status = payload["status"]
    receipt = NotificationReceipt(
        notification_id=notification.id,
        provider=provider,
        event_id=payload["event_id"],
        provider_message_id=payload["provider_message_id"],
        delivery_status=receipt_status,
        payload=payload.get("metadata") or {},
        occurred_at=occurred_at,
    )
    db.add(receipt)
    current_rank = _STATUS_RANK.get(notification.delivery_status, 0)
    incoming_rank = _STATUS_RANK.get(receipt_status, 0)
    if receipt_status == "failed" and notification.delivery_status not in {"delivered", "opened"}:
        notification.delivery_status = "failed"
        notification.status = NotificationStatus.failed
        notification.failed_at = occurred_at
        notification.failure_reason = str((payload.get("metadata") or {}).get("reason") or "Provider reported failure")
    elif incoming_rank >= current_rank:
        notification.delivery_status = receipt_status
        notification.status = NotificationStatus.sent
        if receipt_status == "sent":
            notification.sent_at = notification.sent_at or occurred_at
        elif receipt_status == "delivered":
            notification.delivered_at = occurred_at
        elif receipt_status == "opened":
            notification.delivered_at = notification.delivered_at or occurred_at
            notification.opened_at = occurred_at
    publish_billing_event(
        db,
        owner_user_id=notification.owner_user_id,
        event_type=f"notification.{receipt_status}",
        entity_type="billing_notification",
        entity_id=notification.id,
        payload={"channel": notification.channel, "provider": provider, "delivery_status": notification.delivery_status},
    )
    db.commit()
    return {"duplicate": False, "notification_id": notification.id, "status": notification.delivery_status}


def _canonical(payload: dict) -> bytes:
    normalized = dict(payload)
    occurred_at = normalized.get("occurred_at")
    if isinstance(occurred_at, str):
        try:
            occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    if isinstance(occurred_at, datetime):
        normalized["occurred_at"] = as_utc(occurred_at).isoformat()
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


_STATUS_RANK = {"queued": 0, "processing": 1, "sent": 2, "delivered": 3, "opened": 4}
