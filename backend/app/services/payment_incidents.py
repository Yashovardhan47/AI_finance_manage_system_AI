from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.billing_models import (
    BillingCustomer,
    BillingInvoice,
    BillingNotification,
    BillingPayment,
    BillingPaymentStatus,
    NotificationPreference,
    PaymentIncident,
    PaymentReconciliation,
    TaskDeadLetter,
)
from app.core.config import Settings, get_settings
from app.monitoring import (
    DEAD_LETTERS,
    INCIDENTS_OPENED,
    OPEN_INCIDENTS,
    OUTBOX_OLDEST_SECONDS,
    OUTBOX_QUEUED,
    PAYMENTS_PENDING,
    PAYMENT_RECONCILIATIONS,
)
from app.services.billing_notifications import queue_billing_notification
from app.services.billing_utils import as_utc, utcnow
from app.services.realtime import publish_billing_event


def open_payment_incident(
    db: Session,
    *,
    owner_user_id: int,
    incident_type: str,
    severity: str,
    summary: str,
    details: dict,
    dedupe_key: str,
    customer_id: int | None = None,
    subscription_id: int | None = None,
    invoice_id: int | None = None,
    payment_id: int | None = None,
    now: datetime | None = None,
) -> PaymentIncident:
    observed_at = as_utc(now or utcnow())
    incident = db.scalar(
        select(PaymentIncident).where(
            PaymentIncident.owner_user_id == owner_user_id,
            PaymentIncident.dedupe_key == dedupe_key,
        )
    )
    created = incident is None
    if incident is None:
        incident = PaymentIncident(
            owner_user_id=owner_user_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            invoice_id=invoice_id,
            payment_id=payment_id,
            incident_type=incident_type,
            severity=severity,
            status="open",
            summary=summary,
            details=details,
            dedupe_key=dedupe_key,
            first_detected_at=observed_at,
            last_observed_at=observed_at,
            next_escalation_at=_first_escalation_at(db, owner_user_id, customer_id, observed_at),
        )
        db.add(incident)
    else:
        if incident.status == "resolved":
            incident.status = "open"
            incident.acknowledged_at = None
            incident.resolved_at = None
            incident.escalation_level = 0
            incident.next_escalation_at = _first_escalation_at(db, owner_user_id, customer_id, observed_at)
            created = True
        incident.last_observed_at = observed_at
        incident.summary = summary
        incident.details = {**(incident.details or {}), **details}
        incident.severity = severity
    db.flush()
    publish_billing_event(
        db,
        owner_user_id=owner_user_id,
        event_type="incident.opened" if created else "incident.updated",
        entity_type="payment_incident",
        entity_id=incident.id,
        payload={"incident_type": incident_type, "severity": severity, "status": incident.status},
    )
    if created:
        INCIDENTS_OPENED.labels(incident_type, severity).inc()
    return incident


def acknowledge_incident(db: Session, incident: PaymentIncident, *, at: datetime | None = None) -> PaymentIncident:
    if incident.status == "resolved":
        return incident
    incident.status = "acknowledged"
    incident.acknowledged_at = as_utc(at or utcnow())
    incident.next_escalation_at = None
    publish_billing_event(
        db,
        owner_user_id=incident.owner_user_id,
        event_type="incident.acknowledged",
        entity_type="payment_incident",
        entity_id=incident.id,
        payload={"status": incident.status},
    )
    return incident


def resolve_incident(db: Session, incident: PaymentIncident, *, at: datetime | None = None) -> PaymentIncident:
    incident.status = "resolved"
    incident.resolved_at = as_utc(at or utcnow())
    incident.next_escalation_at = None
    publish_billing_event(
        db,
        owner_user_id=incident.owner_user_id,
        event_type="incident.resolved",
        entity_type="payment_incident",
        entity_id=incident.id,
        payload={"status": incident.status},
    )
    return incident


def resolve_invoice_incidents(
    db: Session,
    *,
    owner_user_id: int,
    invoice_id: int,
    at: datetime | None = None,
) -> int:
    incidents = list(
        db.scalars(
            select(PaymentIncident).where(
                PaymentIncident.owner_user_id == owner_user_id,
                PaymentIncident.invoice_id == invoice_id,
                PaymentIncident.status != "resolved",
            )
        )
    )
    for incident in incidents:
        resolve_incident(db, incident, at=at)
    return len(incidents)


def monitor_pending_payments(
    db: Session,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    checked_at = as_utc(now or utcnow())
    cutoff = checked_at - timedelta(seconds=settings.pending_payment_timeout_seconds)
    payments = list(
        db.scalars(
            select(BillingPayment)
            .options(
                selectinload(BillingPayment.invoice).selectinload(BillingInvoice.customer),
                selectinload(BillingPayment.invoice).selectinload(BillingInvoice.subscription),
            )
            .where(
                BillingPayment.status == BillingPaymentStatus.pending,
                BillingPayment.created_at <= cutoff,
                BillingPayment.timed_out_at.is_(None),
            )
            .order_by(BillingPayment.created_at)
            .with_for_update(skip_locked=True)
            .limit(200)
        )
    )
    for payment in payments:
        payment.processing_state = "timed_out"
        payment.timed_out_at = checked_at
        payment.next_status_check_at = checked_at
        invoice = payment.invoice
        incident = open_payment_incident(
            db,
            owner_user_id=payment.owner_user_id,
            customer_id=invoice.customer_id,
            subscription_id=invoice.subscription_id,
            invoice_id=invoice.id,
            payment_id=payment.id,
            incident_type="payment_confirmation_timeout",
            severity="critical",
            summary=f"Payment confirmation timed out for {invoice.invoice_number}",
            details={"gateway": payment.gateway, "gateway_reference": payment.gateway_reference},
            dedupe_key=f"payment:{payment.id}:confirmation_timeout",
            now=checked_at,
        )
        queue_billing_notification(
            db,
            owner_user_id=payment.owner_user_id,
            customer=invoice.customer,
            event_type="payment_confirmation_timeout",
            invoice=invoice,
            payload={
                "invoice_number": invoice.invoice_number,
                "summary": incident.summary,
                "payment_id": payment.id,
            },
            idempotency_key=f"payment-timeout:{payment.id}",
        )
    db.commit()
    return {"timed_out": len(payments), "checked_at": checked_at.isoformat()}


def poll_gateway_payments(
    db: Session,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    checked_at = as_utc(now or utcnow())
    rows = list(
        db.scalars(
            select(BillingPayment)
            .options(selectinload(BillingPayment.invoice).selectinload(BillingInvoice.customer))
            .where(
                BillingPayment.status == BillingPaymentStatus.pending,
                or_(BillingPayment.next_status_check_at.is_(None), BillingPayment.next_status_check_at <= checked_at),
                BillingPayment.processing_state != "polling",
            )
            .order_by(BillingPayment.created_at)
            .with_for_update(skip_locked=True)
            .limit(100)
        )
    )
    for payment in rows:
        payment.processing_state = "polling"
        payment.last_status_check_at = checked_at
    db.commit()

    counts = {"checked": len(rows), "succeeded": 0, "failed": 0, "pending": 0, "errors": 0}
    for claimed in rows:
        payment = db.get(BillingPayment, claimed.id)
        if not payment or payment.status != BillingPaymentStatus.pending:
            continue
        previous = payment.status.value
        check_id = f"poll_{payment.id}_{uuid4().hex}"
        try:
            provider_status, provider_payload = _gateway_status(payment, settings)
            resolved_status = _apply_provider_status(db, payment, provider_status, check_id, settings)
            payment.provider_status = provider_status
            payment.last_status_check_at = checked_at
            payment.next_status_check_at = checked_at + timedelta(seconds=settings.gateway_poll_interval_seconds)
            payment.processing_state = "reconciled" if resolved_status != "pending" else "pending_provider_confirmation"
            if resolved_status != "pending":
                payment.reconciled_at = checked_at
                _resolve_timeout_incident(db, payment, checked_at)
            counts[resolved_status] += 1
            PAYMENT_RECONCILIATIONS.labels(payment.gateway, resolved_status).inc()
        except Exception as exc:
            provider_status = "poll_error"
            provider_payload = {"error": str(exc)[:1000]}
            resolved_status = "pending"
            payment.processing_state = "poll_error"
            payment.next_status_check_at = checked_at + timedelta(seconds=settings.gateway_poll_interval_seconds)
            counts["errors"] += 1
            open_payment_incident(
                db,
                owner_user_id=payment.owner_user_id,
                customer_id=payment.invoice.customer_id,
                subscription_id=payment.invoice.subscription_id,
                invoice_id=payment.invoice_id,
                payment_id=payment.id,
                incident_type="gateway_status_poll_failed",
                severity="warning",
                summary=f"Gateway status poll failed for payment {payment.id}",
                details=provider_payload,
                dedupe_key=f"payment:{payment.id}:gateway_poll_failed",
                now=checked_at,
            )
            PAYMENT_RECONCILIATIONS.labels(payment.gateway, "error").inc()
        db.add(
            PaymentReconciliation(
                owner_user_id=payment.owner_user_id,
                payment_id=payment.id,
                provider_check_id=check_id,
                previous_status=previous,
                provider_status=provider_status,
                resolved_status=resolved_status,
                provider_payload=provider_payload,
                checked_at=checked_at,
            )
        )
        publish_billing_event(
            db,
            owner_user_id=payment.owner_user_id,
            event_type="payment.reconciled",
            entity_type="billing_payment",
            entity_id=payment.id,
            payload={"provider_status": provider_status, "resolved_status": resolved_status},
        )
        db.commit()
    return counts | {"checked_at": checked_at.isoformat()}


def escalate_due_incidents(db: Session, *, now: datetime | None = None) -> dict:
    escalated_at = as_utc(now or utcnow())
    incidents = list(
        db.scalars(
            select(PaymentIncident)
            .where(
                PaymentIncident.status == "open",
                PaymentIncident.next_escalation_at.is_not(None),
                PaymentIncident.next_escalation_at <= escalated_at,
            )
            .order_by(PaymentIncident.next_escalation_at)
            .with_for_update(skip_locked=True)
            .limit(100)
        )
    )
    delivered = 0
    for incident in incidents:
        if not incident.customer_id:
            incident.next_escalation_at = None
            continue
        preference = db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.owner_user_id == incident.owner_user_id,
                NotificationPreference.customer_id == incident.customer_id,
            )
        )
        rules = (preference.escalation_rules if preference else None) or [
            {"after_minutes": 5, "channels": ["email"]}
        ]
        rule_index = min(incident.escalation_level, len(rules) - 1)
        rule = rules[rule_index]
        customer = db.get(BillingCustomer, incident.customer_id)
        invoice = db.get(BillingInvoice, incident.invoice_id) if incident.invoice_id else None
        if customer:
            queued = queue_billing_notification(
                db,
                owner_user_id=incident.owner_user_id,
                customer=customer,
                event_type="payment_incident_escalated",
                invoice=invoice,
                payload={"summary": incident.summary, "severity": incident.severity, "incident_id": incident.id},
                channels_override=list(rule.get("channels") or ["email"]),
                escalation_level=incident.escalation_level + 1,
                idempotency_key=f"incident:{incident.id}:level:{incident.escalation_level + 1}",
            )
            delivered += int(queued is not None)
        incident.escalation_level += 1
        if incident.escalation_level < len(rules):
            next_rule = rules[incident.escalation_level]
            incident.next_escalation_at = incident.first_detected_at + timedelta(
                minutes=max(1, int(next_rule.get("after_minutes", 5)))
            )
        else:
            incident.next_escalation_at = None
        publish_billing_event(
            db,
            owner_user_id=incident.owner_user_id,
            event_type="incident.escalated",
            entity_type="payment_incident",
            entity_id=incident.id,
            payload={"escalation_level": incident.escalation_level},
        )
    db.commit()
    return {"incidents": len(incidents), "notifications_queued": delivered}


def queue_health_snapshot(db: Session, *, owner_user_id: int | None = None) -> dict:
    now = utcnow()
    notification_filter = [BillingNotification.delivery_status.in_(["queued", "retry_scheduled", "processing"])]
    payment_filter = [BillingPayment.status == BillingPaymentStatus.pending]
    incident_filter = [PaymentIncident.status.in_(["open", "acknowledged"])]
    if owner_user_id is not None:
        notification_filter.append(BillingNotification.owner_user_id == owner_user_id)
        payment_filter.append(BillingPayment.owner_user_id == owner_user_id)
        incident_filter.append(PaymentIncident.owner_user_id == owner_user_id)
    queued, oldest = db.execute(
        select(func.count(BillingNotification.id), func.min(BillingNotification.created_at)).where(*notification_filter)
    ).one()
    pending = db.scalar(select(func.count(BillingPayment.id)).where(*payment_filter)) or 0
    incidents = db.scalar(select(func.count(PaymentIncident.id)).where(*incident_filter)) or 0
    dead_filter = [TaskDeadLetter.status == "unresolved"]
    dead_letters = db.scalar(select(func.count(TaskDeadLetter.id)).where(*dead_filter)) or 0
    oldest_age = max(0, (now - as_utc(oldest)).total_seconds()) if oldest else 0
    snapshot = {
        "status": "degraded" if dead_letters or incidents else "healthy",
        "queued_notifications": int(queued or 0),
        "oldest_notification_seconds": round(oldest_age, 1),
        "pending_payments": int(pending),
        "open_incidents": int(incidents),
        "unresolved_dead_letters": int(dead_letters),
        "generated_at": now.isoformat(),
    }
    OUTBOX_QUEUED.set(snapshot["queued_notifications"])
    OUTBOX_OLDEST_SECONDS.set(snapshot["oldest_notification_seconds"])
    PAYMENTS_PENDING.set(snapshot["pending_payments"])
    DEAD_LETTERS.set(snapshot["unresolved_dead_letters"])
    OPEN_INCIDENTS.set(snapshot["open_incidents"])
    return snapshot


def monitor_queue_health(db: Session, *, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    owners = list(
        db.scalars(
            select(BillingNotification.owner_user_id)
            .where(BillingNotification.delivery_status.in_(["queued", "retry_scheduled", "processing"]))
            .distinct()
        )
    )
    alerted = 0
    for owner_id in owners:
        health = queue_health_snapshot(db, owner_user_id=owner_id)
        unhealthy = (
            health["queued_notifications"] >= settings.queue_backlog_alert_threshold
            or health["oldest_notification_seconds"] >= settings.queue_oldest_alert_seconds
        )
        incident = db.scalar(
            select(PaymentIncident).where(
                PaymentIncident.owner_user_id == owner_id,
                PaymentIncident.dedupe_key == "queue:notification_outbox:health",
            )
        )
        if unhealthy:
            open_payment_incident(
                db,
                owner_user_id=owner_id,
                incident_type="notification_queue_unhealthy",
                severity="critical",
                summary="Notification outbox exceeded its health threshold",
                details=health,
                dedupe_key="queue:notification_outbox:health",
            )
            alerted += 1
        elif incident and incident.status != "resolved":
            resolve_incident(db, incident)
    db.commit()
    return {"owners_checked": len(owners), "alerts": alerted, "global": queue_health_snapshot(db)}


def _first_escalation_at(
    db: Session, owner_user_id: int, customer_id: int | None, detected_at: datetime
) -> datetime | None:
    if customer_id is None:
        return None
    preference = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.owner_user_id == owner_user_id,
            NotificationPreference.customer_id == customer_id,
        )
    )
    rules = preference.escalation_rules if preference else [{"after_minutes": 5, "channels": ["email"]}]
    if not rules:
        return None
    return detected_at + timedelta(minutes=max(1, int(rules[0].get("after_minutes", 5))))


def _gateway_status(payment: BillingPayment, settings: Settings) -> tuple[str, dict]:
    if payment.gateway == "mock_gateway" or not settings.gateway_status_base_url:
        status = (payment.provider_status or "pending").lower()
        return status, {"source": "sandbox", "gateway_reference": payment.gateway_reference, "status": status}
    reference = payment.gateway_reference or payment.gateway_event_id
    headers = {"Authorization": f"Bearer {settings.gateway_status_token}"} if settings.gateway_status_token else {}
    response = httpx.get(
        f"{settings.gateway_status_base_url.rstrip('/')}/{reference}", headers=headers, timeout=15
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("status", "pending")).lower(), payload


def _apply_provider_status(
    db: Session,
    payment: BillingPayment,
    provider_status: str,
    check_id: str,
    settings: Settings,
) -> str:
    success_states = {"paid", "succeeded", "success", "captured", "settled"}
    failed_states = {"failed", "declined", "cancelled", "canceled", "expired"}
    if provider_status not in success_states | failed_states:
        return "pending"
    from app.services.billing_engine import process_gateway_event, sign_webhook

    event_type = "payment.paid" if provider_status in success_states else "payment.failed"
    payload = {
        "event_id": check_id,
        "event_type": event_type,
        "owner_user_id": payment.owner_user_id,
        "invoice_id": payment.invoice_id,
        "amount": str(Decimal(payment.amount)),
        "currency": payment.currency,
        "gateway_reference": payment.gateway_reference or check_id,
        "attempt_number": payment.attempt_number,
        "idempotency_key": payment.idempotency_key,
        "failure_code": None if event_type == "payment.paid" else provider_status,
        "failure_reason": None if event_type == "payment.paid" else f"Gateway reported {provider_status}",
    }
    process_gateway_event(db, payload=payload, signature=sign_webhook(payload, settings.billing_webhook_secret), settings=settings)
    return "succeeded" if event_type == "payment.paid" else "failed"


def _resolve_timeout_incident(db: Session, payment: BillingPayment, at: datetime) -> None:
    incident = db.scalar(
        select(PaymentIncident).where(
            PaymentIncident.owner_user_id == payment.owner_user_id,
            PaymentIncident.dedupe_key == f"payment:{payment.id}:confirmation_timeout",
            PaymentIncident.status != "resolved",
        )
    )
    if incident:
        resolve_incident(db, incident, at=at)
