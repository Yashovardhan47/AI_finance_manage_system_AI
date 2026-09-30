from __future__ import annotations

import hashlib
import hmac
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.billing_models import (
    BillingCustomer,
    BillingInvoice,
    BillingNotification,
    BillingPayment,
    BillingPaymentStatus,
    BillingPlan,
    BillingRefund,
    BillingSubscription,
    BillingWebhookEvent,
    InvoiceLineItem,
    InvoiceLineType,
    InvoiceStatus,
    PaymentRetry,
    RefundStatus,
    RetryStatus,
    SubscriptionStatus,
    TaxRate,
)
from app.core.config import Settings, get_settings
from app.services.audit import write_audit
from app.services.billing_notifications import queue_billing_notification
from app.services.billing_utils import add_billing_period, as_utc, money, period_fraction_remaining, utcnow
from app.services.invoicing import create_invoice
from app.services.subscription_state import InvalidSubscriptionTransition, transition_subscription


def canonical_webhook_body(payload: dict) -> bytes:
    return json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":")).encode()


def sign_webhook(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode(), canonical_webhook_body(payload), hashlib.sha256).hexdigest()


def verify_webhook_signature(payload: dict, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = sign_webhook(payload, secret)
    return hmac.compare_digest(signature, expected)


def process_gateway_event(
    db: Session,
    *,
    payload: dict,
    signature: str | None,
    require_signature: bool = True,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    if require_signature and not verify_webhook_signature(payload, signature, settings.billing_webhook_secret):
        raise ValueError("Invalid mock gateway webhook signature")

    event_id = str(payload["event_id"])
    existing_event = db.scalar(
        select(BillingWebhookEvent).where(
            BillingWebhookEvent.gateway == "mock_gateway", BillingWebhookEvent.event_id == event_id
        )
    )
    if existing_event:
        return {"duplicate": True, "event_id": event_id, "status": existing_event.status}

    owner_user_id = int(payload["owner_user_id"])
    invoice = db.scalar(
        select(BillingInvoice)
        .options(
            selectinload(BillingInvoice.customer),
            selectinload(BillingInvoice.subscription).selectinload(BillingSubscription.plan),
            selectinload(BillingInvoice.retries),
        )
        .where(BillingInvoice.id == int(payload["invoice_id"]), BillingInvoice.owner_user_id == owner_user_id)
    )
    if not invoice:
        raise ValueError("Invoice not found for webhook owner")

    event = BillingWebhookEvent(
        owner_user_id=owner_user_id,
        gateway="mock_gateway",
        event_id=event_id,
        event_type=str(payload["event_type"]),
        signature=signature,
        payload=_jsonable(payload),
        status="processing",
    )
    db.add(event)
    db.flush()

    payment = db.scalar(
        select(BillingPayment).where(
            BillingPayment.owner_user_id == owner_user_id,
            BillingPayment.idempotency_key == str(payload["idempotency_key"]),
        )
    )
    if not payment:
        payment = BillingPayment(
            owner_user_id=owner_user_id,
            invoice_id=invoice.id,
            amount=money(payload["amount"]),
            currency=str(payload.get("currency", invoice.currency)).upper(),
            gateway="mock_gateway",
            gateway_event_id=event_id,
            gateway_reference=str(payload["gateway_reference"]),
            idempotency_key=str(payload["idempotency_key"]),
            attempt_number=int(payload.get("attempt_number", 0)),
            status=BillingPaymentStatus.pending,
        )
        db.add(payment)
        db.flush()

    event_type = str(payload["event_type"])
    amount = money(payload["amount"])
    now = utcnow()
    if event_type == "payment.paid":
        payment.status = BillingPaymentStatus.succeeded
        payment.processed_at = now
        payment.failure_code = None
        payment.failure_reason = None
        invoice.amount_paid = money(min(Decimal(invoice.total), Decimal(invoice.amount_paid) + amount))
        if invoice.amount_paid >= invoice.total:
            invoice.status = InvoiceStatus.paid
            invoice.paid_at = now
            invoice.failed_at = None
        subscription = invoice.subscription
        if SubscriptionStatus(subscription.status) in {SubscriptionStatus.trial, SubscriptionStatus.past_due}:
            try:
                transition_subscription(subscription, SubscriptionStatus.active, at=now)
            except InvalidSubscriptionTransition:
                pass
        for retry in invoice.retries:
            if retry.attempt_number == payment.attempt_number and payment.attempt_number:
                retry.status = RetryStatus.succeeded
                retry.payment_id = payment.id
                retry.processed_at = now
            elif retry.status == RetryStatus.queued:
                retry.status = RetryStatus.cancelled
        queue_billing_notification(
            db,
            owner_user_id=owner_user_id,
            customer=invoice.customer,
            event_type="payment_received",
            invoice=invoice,
            payload={"invoice_number": invoice.invoice_number, "amount": str(amount)},
        )
        action = "billing.payment.received"
    elif event_type == "payment.failed":
        payment.status = BillingPaymentStatus.failed
        payment.processed_at = now
        payment.failure_code = payload.get("failure_code") or "mock_declined"
        payment.failure_reason = payload.get("failure_reason") or "Mock gateway declined the payment"
        invoice.status = InvoiceStatus.failed
        invoice.failed_at = now
        subscription = invoice.subscription
        if SubscriptionStatus(subscription.status) == SubscriptionStatus.active:
            transition_subscription(subscription, SubscriptionStatus.past_due, at=now)
        _mark_or_schedule_retries(db, invoice=invoice, payment=payment, settings=settings, now=now)
        queue_billing_notification(
            db,
            owner_user_id=owner_user_id,
            customer=invoice.customer,
            event_type="payment_failed",
            invoice=invoice,
            payload={
                "invoice_number": invoice.invoice_number,
                "reason": payment.failure_reason,
                "next_retry": _next_retry_iso(invoice.retries),
            },
        )
        action = "billing.payment.failed"
    elif event_type == "payment.refunded":
        payment.status = BillingPaymentStatus.refunded
        payment.processed_at = now
        invoice.amount_refunded = money(Decimal(invoice.amount_refunded) + amount)
        invoice.status = InvoiceStatus.refunded if invoice.amount_refunded >= invoice.amount_paid else InvoiceStatus.partially_refunded
        queue_billing_notification(
            db,
            owner_user_id=owner_user_id,
            customer=invoice.customer,
            event_type="refund_issued",
            invoice=invoice,
            payload={"invoice_number": invoice.invoice_number, "amount": str(amount)},
        )
        action = "billing.refund.webhook_received"
    else:
        event.status = "ignored"
        event.error = "Unsupported event type"
        event.processed_at = now
        raise ValueError("Unsupported gateway event type")

    event.status = "processed"
    event.processed_at = now
    write_audit(
        db,
        user_id=owner_user_id,
        action=action,
        entity_type="billing_payment",
        entity_id=payment.id,
        detail={
            "customer_id": invoice.customer_id,
            "subscription_id": invoice.subscription_id,
            "invoice_id": invoice.id,
            "event_id": event_id,
            "amount": str(amount),
            "attempt_number": payment.attempt_number,
        },
    )
    return {
        "duplicate": False,
        "event_id": event_id,
        "event_type": event_type,
        "invoice_id": invoice.id,
        "invoice_status": invoice.status.value,
        "payment_id": payment.id,
        "payment_status": payment.status.value,
        "subscription_status": invoice.subscription.status.value,
    }


def simulate_gateway_charge(
    db: Session,
    *,
    invoice: BillingInvoice,
    idempotency_key: str,
    outcome: str | None = None,
    failure_reason: str | None = None,
    attempt_number: int = 0,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    existing = db.scalar(
        select(BillingPayment).where(
            BillingPayment.owner_user_id == invoice.owner_user_id,
            BillingPayment.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return {
            "duplicate": True,
            "payment_id": existing.id,
            "payment_status": existing.status.value,
            "invoice_id": invoice.id,
            "invoice_status": invoice.status.value,
        }
    selected = outcome or ("success" if random.random() <= settings.mock_payment_success_rate else "failure")
    event_type = "payment.paid" if selected == "success" else "payment.failed"
    payload = {
        "event_id": f"evt_{uuid4().hex}",
        "event_type": event_type,
        "owner_user_id": invoice.owner_user_id,
        "invoice_id": invoice.id,
        "amount": str(max(Decimal(invoice.total) - Decimal(invoice.amount_paid), Decimal("0.01"))),
        "currency": invoice.currency,
        "gateway_reference": f"mock_{uuid4().hex[:20]}",
        "attempt_number": attempt_number,
        "idempotency_key": idempotency_key,
        "failure_code": None if selected == "success" else "mock_declined",
        "failure_reason": None if selected == "success" else (failure_reason or "Configurable mock gateway failure"),
    }
    signature = sign_webhook(payload, settings.billing_webhook_secret)
    result = process_gateway_event(db, payload=payload, signature=signature, settings=settings)
    result.update({"signed_webhook": {"payload": payload, "signature": signature}, "delivery": "verified_internal_webhook"})
    return result


def run_due_retries(
    db: Session,
    *,
    as_of: datetime | None = None,
    owner_user_id: int | None = None,
    forced_outcome: str | None = None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    now = as_utc(as_of or utcnow())
    query = (
        select(PaymentRetry)
        .options(
            selectinload(PaymentRetry.invoice).selectinload(BillingInvoice.subscription),
            selectinload(PaymentRetry.invoice).selectinload(BillingInvoice.customer),
            selectinload(PaymentRetry.invoice).selectinload(BillingInvoice.retries),
        )
        .where(PaymentRetry.status == RetryStatus.queued, PaymentRetry.scheduled_for <= now)
        .order_by(PaymentRetry.scheduled_for, PaymentRetry.attempt_number)
    )
    if owner_user_id is not None:
        query = query.where(PaymentRetry.owner_user_id == owner_user_id)
    retries = list(db.scalars(query))
    results: list[dict] = []
    for retry in retries:
        if retry.invoice.status == InvoiceStatus.paid:
            retry.status = RetryStatus.cancelled
            continue
        retry.status = RetryStatus.processing
        result = simulate_gateway_charge(
            db,
            invoice=retry.invoice,
            idempotency_key=f"retry:{retry.id}:{retry.attempt_number}",
            outcome=forced_outcome,
            attempt_number=retry.attempt_number,
            settings=settings,
        )
        results.append(result)
    db.commit()
    return {"processed": len(results), "results": results, "as_of": now.isoformat()}


def issue_refund(
    db: Session,
    *,
    invoice: BillingInvoice,
    amount: Decimal | None,
    reason: str,
) -> BillingRefund:
    refundable = money(max(Decimal(invoice.amount_paid) - Decimal(invoice.amount_refunded), Decimal("0")))
    requested = refundable if amount is None else money(amount)
    if requested <= 0:
        raise ValueError("No refundable balance remains on this invoice")
    if requested > refundable:
        raise ValueError(f"Refund exceeds the refundable balance of {refundable}")
    now = utcnow()
    payment = db.scalar(
        select(BillingPayment)
        .where(BillingPayment.invoice_id == invoice.id, BillingPayment.status == BillingPaymentStatus.succeeded)
        .order_by(BillingPayment.processed_at.desc())
    )
    refund = BillingRefund(
        owner_user_id=invoice.owner_user_id,
        invoice_id=invoice.id,
        payment_id=payment.id if payment else None,
        amount=requested,
        reason=reason,
        status=RefundStatus.succeeded,
        gateway_reference=f"refund_{uuid4().hex[:20]}",
        processed_at=now,
    )
    db.add(refund)
    db.flush()
    db.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            line_type=InvoiceLineType.refund,
            description=f"Refund: {reason}",
            quantity=Decimal("1"),
            unit_amount=-requested,
            amount=-requested,
            metadata_json={"refund_id": refund.id},
        )
    )
    invoice.amount_refunded = money(Decimal(invoice.amount_refunded) + requested)
    invoice.status = InvoiceStatus.refunded if invoice.amount_refunded >= invoice.amount_paid else InvoiceStatus.partially_refunded
    invoice.pdf_data = None
    invoice.pdf_sha256 = None
    invoice.pdf_generated_at = None
    queue_billing_notification(
        db,
        owner_user_id=invoice.owner_user_id,
        customer=invoice.customer,
        event_type="refund_issued",
        invoice=invoice,
        payload={"invoice_number": invoice.invoice_number, "amount": str(requested), "reason": reason},
    )
    write_audit(
        db,
        user_id=invoice.owner_user_id,
        action="billing.refund.issued",
        entity_type="billing_refund",
        entity_id=refund.id,
        detail={"customer_id": invoice.customer_id, "invoice_id": invoice.id, "amount": str(requested), "reason": reason},
    )
    return refund


def unused_period_refund_amount(subscription: BillingSubscription, invoice: BillingInvoice, *, at: datetime | None = None) -> Decimal:
    fraction = period_fraction_remaining(subscription.current_period_start, subscription.current_period_end, at or utcnow())
    paid_available = max(Decimal(invoice.amount_paid) - Decimal(invoice.amount_refunded), Decimal("0"))
    return money(min(paid_available, Decimal(subscription.plan.price) * subscription.quantity * fraction))


def billing_dashboard(db: Session, *, owner_user_id: int, months: int = 12) -> dict:
    now = utcnow()
    subscriptions = list(
        db.scalars(
            select(BillingSubscription)
            .options(selectinload(BillingSubscription.plan), selectinload(BillingSubscription.customer))
            .where(BillingSubscription.owner_user_id == owner_user_id)
        )
    )
    invoices = list(
        db.scalars(
            select(BillingInvoice)
            .options(
                selectinload(BillingInvoice.subscription).selectinload(BillingSubscription.plan),
                selectinload(BillingInvoice.customer),
            )
            .where(BillingInvoice.owner_user_id == owner_user_id)
            .order_by(BillingInvoice.created_at.desc())
        )
    )
    retries = list(
        db.scalars(
            select(PaymentRetry)
            .options(selectinload(PaymentRetry.invoice))
            .where(PaymentRetry.owner_user_id == owner_user_id)
            .order_by(PaymentRetry.scheduled_for)
        )
    )
    active = [item for item in subscriptions if item.status == SubscriptionStatus.active]
    monthly_recurring_revenue = sum(
        (
            Decimal(item.plan.price) * item.quantity / (Decimal("12") if item.plan.billing_interval.value == "annual" else Decimal("1"))
            for item in active
        ),
        Decimal("0"),
    )
    window_start = now - timedelta(days=30)
    recent_cancelled = [item for item in subscriptions if item.cancelled_at and as_utc(item.cancelled_at) >= window_start]
    churn_denominator = len(active) + len(recent_cancelled)
    churn_rate = (len(recent_cancelled) / churn_denominator * 100) if churn_denominator else 0
    ended_trials = [item for item in subscriptions if item.trial_ends_at and as_utc(item.trial_ends_at) <= now]
    converted_trials = [item for item in ended_trials if item.activated_at]
    trial_conversion = (len(converted_trials) / len(ended_trials) * 100) if ended_trials else 0

    invoice_status = defaultdict(int)
    revenue_by_plan = defaultdict(Decimal)
    revenue_by_month = defaultdict(Decimal)
    cutoff_month = _month_key(now - timedelta(days=months * 31))
    for invoice in invoices:
        invoice_status[invoice.status.value] += 1
        if invoice.amount_paid > 0:
            revenue_by_plan[invoice.subscription.plan.name] += Decimal(invoice.amount_paid) - Decimal(invoice.amount_refunded)
            month_key = _month_key(invoice.paid_at or invoice.created_at)
            if month_key >= cutoff_month:
                revenue_by_month[month_key] += Decimal(invoice.amount_paid) - Decimal(invoice.amount_refunded)

    queued = [item for item in retries if item.status in {RetryStatus.queued, RetryStatus.processing}]
    return {
        "generated_at": now.isoformat(),
        "metrics": {
            "active_subscriptions": len(active),
            "trial_subscriptions": len([item for item in subscriptions if item.status == SubscriptionStatus.trial]),
            "past_due_subscriptions": len([item for item in subscriptions if item.status == SubscriptionStatus.past_due]),
            "cancelled_subscriptions": len([item for item in subscriptions if item.status == SubscriptionStatus.cancelled]),
            "mrr": float(money(monthly_recurring_revenue)),
            "churn_rate_percent": round(churn_rate, 2),
            "trial_conversion_percent": round(trial_conversion, 2),
            "outstanding_revenue": float(money(sum((Decimal(item.total) - Decimal(item.amount_paid) for item in invoices if item.status in {InvoiceStatus.open, InvoiceStatus.failed}), Decimal("0")))),
            "queued_retries": len(queued),
        },
        "invoice_status": [{"status": key, "count": value} for key, value in sorted(invoice_status.items())],
        "revenue_by_plan": [{"plan": key, "revenue": float(money(value))} for key, value in sorted(revenue_by_plan.items())],
        "revenue_trend": [{"month": key, "revenue": float(money(value))} for key, value in sorted(revenue_by_month.items())],
        "retry_queue": [_retry_dict(item) for item in queued[:20]],
        "recent_invoices": [_invoice_summary(item) for item in invoices[:20]],
        "lifecycle": [{"status": status.value, "count": len([item for item in subscriptions if item.status == status])} for status in SubscriptionStatus],
    }


def tax_summary(db: Session, *, owner_user_id: int, start: datetime | None = None, end: datetime | None = None) -> dict:
    query = (
        select(InvoiceLineItem, BillingInvoice, BillingCustomer)
        .join(BillingInvoice, InvoiceLineItem.invoice_id == BillingInvoice.id)
        .join(BillingCustomer, BillingInvoice.customer_id == BillingCustomer.id)
        .where(BillingInvoice.owner_user_id == owner_user_id, InvoiceLineItem.line_type == InvoiceLineType.tax)
    )
    if start:
        query = query.where(BillingInvoice.created_at >= as_utc(start))
    if end:
        query = query.where(BillingInvoice.created_at <= as_utc(end))
    rows = db.execute(query).all()
    grouped: dict[tuple, Decimal] = defaultdict(Decimal)
    for line, invoice, customer in rows:
        grouped[(customer.country_code, customer.region or "All", line.description, invoice.currency)] += Decimal(line.amount)
    return {
        "total_tax": float(money(sum(grouped.values(), Decimal("0")))),
        "items": [
            {"country_code": key[0], "region": key[1], "tax": key[2], "currency": key[3], "amount": float(money(value))}
            for key, value in sorted(grouped.items())
        ],
    }


def _mark_or_schedule_retries(
    db: Session,
    *,
    invoice: BillingInvoice,
    payment: BillingPayment,
    settings: Settings,
    now: datetime,
) -> None:
    existing_by_attempt = {item.attempt_number: item for item in invoice.retries}
    if payment.attempt_number:
        retry = existing_by_attempt.get(payment.attempt_number)
        if retry:
            retry.status = RetryStatus.failed
            retry.payment_id = payment.id
            retry.last_error = payment.failure_reason
            retry.processed_at = now
    for attempt, day in enumerate(settings.retry_schedule_days, start=1):
        if attempt not in existing_by_attempt:
            retry = PaymentRetry(
                owner_user_id=invoice.owner_user_id,
                invoice_id=invoice.id,
                subscription_id=invoice.subscription_id,
                attempt_number=attempt,
                scheduled_for=now + timedelta(days=day),
                status=RetryStatus.queued,
            )
            db.add(retry)
            invoice.retries.append(retry)
    if payment.attempt_number >= len(settings.retry_schedule_days) and settings.retry_schedule_days:
        for retry in invoice.retries:
            if retry.status == RetryStatus.queued:
                retry.status = RetryStatus.cancelled
        if SubscriptionStatus(invoice.subscription.status) != SubscriptionStatus.cancelled:
            transition_subscription(
                invoice.subscription,
                SubscriptionStatus.cancelled,
                at=now,
                reason="Payment recovery exhausted",
            )
        queue_billing_notification(
            db,
            owner_user_id=invoice.owner_user_id,
            customer=invoice.customer,
            event_type="subscription_cancelled_after_retries",
            invoice=invoice,
            payload={"invoice_number": invoice.invoice_number, "attempts": len(settings.retry_schedule_days)},
        )


def _next_retry_iso(retries: list[PaymentRetry]) -> str | None:
    queued = sorted((item for item in retries if item.status == RetryStatus.queued), key=lambda item: item.scheduled_for)
    return queued[0].scheduled_for.isoformat() if queued else None


def _jsonable(value):
    return json.loads(json.dumps(value, default=str))


def _month_key(value: datetime) -> str:
    return as_utc(value).strftime("%Y-%m")


def _retry_dict(item: PaymentRetry) -> dict:
    return {
        "id": item.id,
        "invoice_id": item.invoice_id,
        "invoice_number": item.invoice.invoice_number,
        "attempt_number": item.attempt_number,
        "scheduled_for": item.scheduled_for.isoformat(),
        "status": item.status.value,
        "last_error": item.last_error,
    }


def _invoice_summary(item: BillingInvoice) -> dict:
    return {
        "id": item.id,
        "invoice_number": item.invoice_number,
        "customer_id": item.customer_id,
        "customer_name": item.customer.name,
        "subscription_id": item.subscription_id,
        "plan_name": item.subscription.plan.name,
        "status": item.status.value,
        "currency": item.currency,
        "total": float(item.total),
        "amount_paid": float(item.amount_paid),
        "amount_refunded": float(item.amount_refunded),
        "issue_date": item.issue_date.isoformat(),
        "due_date": item.due_date.isoformat(),
        "pdf_available": bool(item.pdf_data),
    }
