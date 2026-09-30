from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.billing_models import (
    BillingCustomer,
    BillingInvoice,
    BillingPlan,
    BillingSubscription,
    InvoiceStatus,
    SubscriptionStatus,
)
from app.services.audit import write_audit
from app.services.billing_engine import issue_refund, unused_period_refund_amount
from app.services.billing_utils import add_billing_period, as_utc, utcnow
from app.services.invoicing import create_proration_invoice
from app.services.subscription_state import transition_subscription


def create_subscription(
    db: Session,
    *,
    owner_user_id: int,
    customer: BillingCustomer,
    plan: BillingPlan,
    quantity: int = 1,
    start_trial: bool = True,
    start_at: datetime | None = None,
) -> BillingSubscription:
    start = as_utc(start_at or utcnow())
    has_trial = bool(start_trial and plan.trial_days > 0)
    if has_trial:
        trial_end = start + timedelta(days=plan.trial_days)
        subscription = BillingSubscription(
            owner_user_id=owner_user_id,
            customer_id=customer.id,
            plan_id=plan.id,
            status=SubscriptionStatus.trial,
            quantity=quantity,
            trial_started_at=start,
            trial_ends_at=trial_end,
            status_changed_at=start,
            current_period_start=start,
            current_period_end=trial_end,
            next_billing_at=trial_end,
        )
    else:
        period_end = add_billing_period(start, plan.billing_interval)
        subscription = BillingSubscription(
            owner_user_id=owner_user_id,
            customer_id=customer.id,
            plan_id=plan.id,
            status=SubscriptionStatus.active,
            quantity=quantity,
            activated_at=start,
            status_changed_at=start,
            current_period_start=start,
            current_period_end=period_end,
            next_billing_at=start,
        )
    subscription.customer = customer
    subscription.plan = plan
    db.add(subscription)
    db.flush()
    write_audit(
        db,
        user_id=owner_user_id,
        action="billing.subscription.created",
        entity_type="billing_subscription",
        entity_id=subscription.id,
        detail={"customer_id": customer.id, "plan_id": plan.id, "status": subscription.status.value},
    )
    return subscription


def change_subscription_plan(
    db: Session,
    *,
    subscription: BillingSubscription,
    new_plan: BillingPlan,
    timing: str,
    at: datetime | None = None,
) -> tuple[BillingInvoice | None, dict | None]:
    if subscription.status == SubscriptionStatus.cancelled:
        raise ValueError("A cancelled subscription cannot change plans")
    if subscription.plan_id == new_plan.id:
        raise ValueError("The subscription already uses this plan")
    if timing == "end_of_cycle":
        subscription.pending_plan_id = new_plan.id
        subscription.pending_plan = new_plan
        subscription.version += 1
        write_audit(
            db,
            user_id=subscription.owner_user_id,
            action="billing.subscription.plan_change_scheduled",
            entity_type="billing_subscription",
            entity_id=subscription.id,
            detail={"customer_id": subscription.customer_id, "from_plan_id": subscription.plan_id, "to_plan_id": new_plan.id, "effective_at": subscription.current_period_end.isoformat()},
        )
        return None, None
    invoice, quote = create_proration_invoice(db, subscription=subscription, new_plan=new_plan, effective_at=at)
    return invoice, quote


def pause_subscription(
    db: Session,
    *,
    subscription: BillingSubscription,
    resume_at: datetime | None = None,
) -> BillingSubscription:
    transition_subscription(subscription, SubscriptionStatus.paused)
    subscription.resumes_at = as_utc(resume_at) if resume_at else None
    write_audit(
        db,
        user_id=subscription.owner_user_id,
        action="billing.subscription.paused",
        entity_type="billing_subscription",
        entity_id=subscription.id,
        detail={"customer_id": subscription.customer_id, "resume_at": subscription.resumes_at.isoformat() if subscription.resumes_at else None},
    )
    return subscription


def resume_subscription(db: Session, *, subscription: BillingSubscription) -> BillingSubscription:
    now = utcnow()
    transition_subscription(subscription, SubscriptionStatus.active, at=now)
    if as_utc(subscription.current_period_end) <= now:
        subscription.next_billing_at = now
    write_audit(
        db,
        user_id=subscription.owner_user_id,
        action="billing.subscription.resumed",
        entity_type="billing_subscription",
        entity_id=subscription.id,
        detail={"customer_id": subscription.customer_id},
    )
    return subscription


def cancel_subscription(
    db: Session,
    *,
    subscription: BillingSubscription,
    timing: str,
    refund_unused: bool,
    reason: str,
) -> tuple[BillingSubscription, int | None]:
    if subscription.status == SubscriptionStatus.cancelled:
        return subscription, None
    if timing == "end_of_cycle":
        subscription.cancel_at_period_end = True
        subscription.cancellation_reason = reason
        subscription.version += 1
        write_audit(
            db,
            user_id=subscription.owner_user_id,
            action="billing.subscription.cancellation_scheduled",
            entity_type="billing_subscription",
            entity_id=subscription.id,
            detail={"customer_id": subscription.customer_id, "effective_at": subscription.current_period_end.isoformat(), "reason": reason},
        )
        return subscription, None

    transition_subscription(subscription, SubscriptionStatus.cancelled, reason=reason)
    refund_id = None
    if refund_unused:
        latest_paid = db.scalar(
            select(BillingInvoice)
            .options(selectinload(BillingInvoice.customer), selectinload(BillingInvoice.subscription).selectinload(BillingSubscription.plan))
            .where(
                BillingInvoice.subscription_id == subscription.id,
                BillingInvoice.status.in_([InvoiceStatus.paid, InvoiceStatus.partially_refunded]),
            )
            .order_by(BillingInvoice.paid_at.desc(), BillingInvoice.id.desc())
        )
        if latest_paid:
            amount = unused_period_refund_amount(subscription, latest_paid)
            if amount > 0:
                refund = issue_refund(db, invoice=latest_paid, amount=amount, reason=f"Unused period refund: {reason}")
                refund_id = refund.id
    write_audit(
        db,
        user_id=subscription.owner_user_id,
        action="billing.subscription.cancelled",
        entity_type="billing_subscription",
        entity_id=subscription.id,
        detail={"customer_id": subscription.customer_id, "timing": "immediate", "reason": reason, "refund_id": refund_id},
    )
    return subscription, refund_id
