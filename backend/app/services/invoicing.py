from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.billing_models import (
    BillingCycle,
    BillingCycleStatus,
    BillingInterval,
    BillingInvoice,
    BillingPlan,
    BillingSubscription,
    InvoiceCounter,
    InvoiceLineItem,
    InvoiceLineType,
    InvoiceStatus,
    SubscriptionStatus,
    UsageRecord,
)
from app.services.audit import write_audit
from app.services.billing_pdf import build_invoice_pdf
from app.services.billing_tax import resolve_tax_rate
from app.services.billing_utils import add_billing_period, as_utc, money, period_fraction_remaining, utcnow
from app.services.subscription_state import transition_subscription


def next_invoice_number(db: Session, *, owner_user_id: int, at: datetime) -> str:
    period_key = as_utc(at).strftime("%Y%m")
    counter = db.scalar(
        select(InvoiceCounter)
        .where(InvoiceCounter.owner_user_id == owner_user_id, InvoiceCounter.period_key == period_key)
        .with_for_update()
    )
    if not counter:
        counter = InvoiceCounter(owner_user_id=owner_user_id, period_key=period_key, current_value=0)
        db.add(counter)
        db.flush()
    counter.current_value += 1
    return f"BF-{period_key}-{counter.current_value:06d}"


def proration_quote(
    *,
    current_plan: BillingPlan,
    new_plan: BillingPlan,
    period_start: datetime,
    period_end: datetime,
    effective_at: datetime,
    quantity: int = 1,
) -> dict:
    fraction = period_fraction_remaining(period_start, period_end, effective_at)
    credit = money(Decimal(current_plan.price) * quantity * fraction)
    debit = money(Decimal(new_plan.price) * quantity * fraction)
    return {
        "fraction_remaining": float(fraction.quantize(Decimal("0.0001"))),
        "unused_current_plan_credit": credit,
        "new_plan_remainder_debit": debit,
        "net_amount": money(debit - credit),
        "effective_at": as_utc(effective_at),
    }


def create_invoice(
    db: Session,
    *,
    subscription: BillingSubscription,
    period_start: datetime,
    period_end: datetime,
    line_specs: list[dict],
    issue_at: datetime | None = None,
    due_days: int = 7,
    apply_customer_credit: bool = True,
) -> BillingInvoice:
    issue_at = as_utc(issue_at or utcnow())
    customer = subscription.customer
    invoice = BillingInvoice(
        owner_user_id=subscription.owner_user_id,
        customer_id=customer.id,
        subscription_id=subscription.id,
        invoice_number=next_invoice_number(db, owner_user_id=subscription.owner_user_id, at=issue_at),
        status=InvoiceStatus.open,
        currency=subscription.plan.currency,
        issue_date=issue_at.date(),
        due_date=(issue_at + timedelta(days=due_days)).date(),
        period_start=as_utc(period_start),
        period_end=as_utc(period_end),
        payment_terms=f"Net {due_days}" if due_days else "Due on receipt",
    )
    db.add(invoice)
    db.flush()

    lines: list[InvoiceLineItem] = []
    for spec in line_specs:
        lines.append(
            InvoiceLineItem(
                invoice_id=invoice.id,
                line_type=InvoiceLineType(spec["line_type"]),
                description=spec["description"],
                quantity=Decimal(str(spec.get("quantity", 1))),
                unit_amount=Decimal(str(spec.get("unit_amount", spec["amount"]))),
                amount=money(spec["amount"]),
                metadata_json=spec.get("metadata", {}),
            )
        )
    db.add_all(lines)

    pre_tax = money(sum((line.amount for line in lines), Decimal("0")))
    if apply_customer_credit and customer.credit_balance > 0 and pre_tax > 0:
        applied = money(min(Decimal(customer.credit_balance), pre_tax))
        credit_line = InvoiceLineItem(
            invoice_id=invoice.id,
            line_type=InvoiceLineType.proration_credit,
            description="Available account credit applied",
            quantity=Decimal("1"),
            unit_amount=-applied,
            amount=-applied,
            metadata_json={"source": "customer_credit_balance"},
        )
        lines.append(credit_line)
        db.add(credit_line)
        customer.credit_balance = money(Decimal(customer.credit_balance) - applied)
        pre_tax = money(pre_tax - applied)

    tax_rate = resolve_tax_rate(
        db,
        owner_user_id=subscription.owner_user_id,
        customer=customer,
        on_date=issue_at.date(),
    )
    tax_amount = Decimal("0")
    if tax_rate and pre_tax > 0:
        tax_amount = money(pre_tax * Decimal(tax_rate.rate_percent) / Decimal("100"))
        tax_line = InvoiceLineItem(
            invoice_id=invoice.id,
            line_type=InvoiceLineType.tax,
            description=f"{tax_rate.name} ({tax_rate.rate_percent}%)",
            quantity=Decimal("1"),
            unit_amount=tax_amount,
            amount=tax_amount,
            tax_rate_percent=tax_rate.rate_percent,
            metadata_json={"tax_rate_id": tax_rate.id, "country": customer.country_code, "region": customer.region},
        )
        lines.append(tax_line)
        db.add(tax_line)

    invoice.subtotal = money(sum((line.amount for line in lines if line.line_type == InvoiceLineType.plan_fee), Decimal("0")))
    invoice.proration_total = money(
        sum(
            (line.amount for line in lines if line.line_type in {InvoiceLineType.proration_credit, InvoiceLineType.proration_debit}),
            Decimal("0"),
        )
    )
    invoice.usage_total = money(sum((line.amount for line in lines if line.line_type == InvoiceLineType.usage), Decimal("0")))
    invoice.tax_total = tax_amount
    invoice.total = money(max(Decimal("0"), sum((line.amount for line in lines), Decimal("0"))))
    if invoice.total == 0:
        invoice.status = InvoiceStatus.paid
        invoice.paid_at = issue_at

    write_audit(
        db,
        user_id=subscription.owner_user_id,
        action="billing.invoice.generated",
        entity_type="billing_invoice",
        entity_id=invoice.id,
        detail={
            "customer_id": customer.id,
            "subscription_id": subscription.id,
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
        },
    )
    return invoice


def create_proration_invoice(
    db: Session,
    *,
    subscription: BillingSubscription,
    new_plan: BillingPlan,
    effective_at: datetime | None = None,
) -> tuple[BillingInvoice, dict]:
    effective_at = as_utc(effective_at or utcnow())
    old_plan = subscription.plan
    quote = proration_quote(
        current_plan=old_plan,
        new_plan=new_plan,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        effective_at=effective_at,
        quantity=subscription.quantity,
    )
    invoice = create_invoice(
        db,
        subscription=subscription,
        period_start=effective_at,
        period_end=subscription.current_period_end,
        issue_at=effective_at,
        due_days=0,
        apply_customer_credit=False,
        line_specs=[
            {
                "line_type": InvoiceLineType.proration_credit,
                "description": f"Unused {old_plan.name} credit",
                "quantity": 1,
                "unit_amount": -quote["unused_current_plan_credit"],
                "amount": -quote["unused_current_plan_credit"],
                "metadata": {"plan_id": old_plan.id, "fraction_remaining": quote["fraction_remaining"]},
            },
            {
                "line_type": InvoiceLineType.proration_debit,
                "description": f"{new_plan.name} for remaining period",
                "quantity": 1,
                "unit_amount": quote["new_plan_remainder_debit"],
                "amount": quote["new_plan_remainder_debit"],
                "metadata": {"plan_id": new_plan.id, "fraction_remaining": quote["fraction_remaining"]},
            },
        ],
    )
    if quote["net_amount"] < 0:
        subscription.customer.credit_balance = money(
            Decimal(subscription.customer.credit_balance) + abs(quote["net_amount"])
        )
        invoice.total = Decimal("0")
        invoice.status = InvoiceStatus.paid
        invoice.paid_at = effective_at
    subscription.plan_id = new_plan.id
    subscription.plan = new_plan
    subscription.pending_plan_id = None
    subscription.version += 1
    write_audit(
        db,
        user_id=subscription.owner_user_id,
        action="billing.subscription.plan_changed",
        entity_type="billing_subscription",
        entity_id=subscription.id,
        detail={
            "customer_id": subscription.customer_id,
            "from_plan_id": old_plan.id,
            "to_plan_id": new_plan.id,
            "timing": "immediate",
            "proration_invoice_id": invoice.id,
            "net_amount": str(quote["net_amount"]),
        },
    )
    return invoice, quote


def process_subscription_cycle(
    db: Session,
    subscription: BillingSubscription,
    *,
    as_of: datetime | None = None,
) -> BillingInvoice | None:
    now = as_utc(as_of or utcnow())
    status = SubscriptionStatus(subscription.status)

    if status == SubscriptionStatus.paused:
        if subscription.resumes_at and as_utc(subscription.resumes_at) <= now:
            transition_subscription(subscription, SubscriptionStatus.active, at=now)
            subscription.next_billing_at = now
        else:
            return None
    if status == SubscriptionStatus.cancelled or status == SubscriptionStatus.past_due:
        return None
    if subscription.cancel_at_period_end and as_utc(subscription.current_period_end) <= now:
        transition_subscription(
            subscription,
            SubscriptionStatus.cancelled,
            at=now,
            reason=subscription.cancellation_reason or "End-of-cycle cancellation",
        )
        write_audit(
            db,
            user_id=subscription.owner_user_id,
            action="billing.subscription.cancelled",
            entity_type="billing_subscription",
            entity_id=subscription.id,
            detail={"customer_id": subscription.customer_id, "timing": "end_of_cycle"},
        )
        return None
    if not subscription.next_billing_at or as_utc(subscription.next_billing_at) > now:
        return None

    if status == SubscriptionStatus.trial:
        transition_subscription(subscription, SubscriptionStatus.active, at=now)

    if subscription.pending_plan_id:
        pending = db.scalar(
            select(BillingPlan).where(
                BillingPlan.id == subscription.pending_plan_id,
                BillingPlan.owner_user_id == subscription.owner_user_id,
                BillingPlan.is_archived.is_(False),
            )
        )
        if pending:
            previous_plan_id = subscription.plan_id
            subscription.plan_id = pending.id
            subscription.plan = pending
            subscription.pending_plan_id = None
            write_audit(
                db,
                user_id=subscription.owner_user_id,
                action="billing.subscription.plan_changed",
                entity_type="billing_subscription",
                entity_id=subscription.id,
                detail={"customer_id": subscription.customer_id, "from_plan_id": previous_plan_id, "to_plan_id": pending.id, "timing": "end_of_cycle"},
            )

    period_start = as_utc(subscription.next_billing_at)
    period_end = add_billing_period(period_start, subscription.plan.billing_interval)
    idempotency_key = f"cycle:{subscription.id}:{period_start.isoformat()}"
    existing_cycle = db.scalar(select(BillingCycle).where(BillingCycle.idempotency_key == idempotency_key))
    if existing_cycle:
        return db.scalar(
            select(BillingInvoice)
            .options(selectinload(BillingInvoice.line_items))
            .where(BillingInvoice.id == existing_cycle.invoice_id)
        ) if existing_cycle.invoice_id else None

    cycle = BillingCycle(
        owner_user_id=subscription.owner_user_id,
        subscription_id=subscription.id,
        status=BillingCycleStatus.processing,
        period_start=period_start,
        period_end=period_end,
        scheduled_for=period_start,
        idempotency_key=idempotency_key,
        attempt_count=1,
    )
    db.add(cycle)
    db.flush()

    plan_amount = money(Decimal(subscription.plan.price) * subscription.quantity)
    line_specs = [
        {
            "line_type": InvoiceLineType.plan_fee,
            "description": f"{subscription.plan.name} - {subscription.plan.billing_interval.value}",
            "quantity": subscription.quantity,
            "unit_amount": subscription.plan.price,
            "amount": plan_amount,
            "metadata": {"plan_id": subscription.plan.id, "billing_interval": subscription.plan.billing_interval.value},
        }
    ]
    usage_records = list(
        db.scalars(
            select(UsageRecord).where(
                UsageRecord.owner_user_id == subscription.owner_user_id,
                UsageRecord.subscription_id == subscription.id,
                UsageRecord.billed_invoice_id.is_(None),
                UsageRecord.occurred_at <= now,
            )
        )
    )
    for usage in usage_records:
        line_specs.append(
            {
                "line_type": InvoiceLineType.usage,
                "description": f"Usage: {usage.metric}",
                "quantity": usage.quantity,
                "unit_amount": usage.unit_price,
                "amount": money(Decimal(usage.quantity) * Decimal(usage.unit_price)),
                "metadata": {"usage_record_id": usage.id, "metric": usage.metric},
            }
        )

    invoice = create_invoice(
        db,
        subscription=subscription,
        period_start=period_start,
        period_end=period_end,
        line_specs=line_specs,
        issue_at=now,
    )
    cycle.invoice_id = invoice.id
    cycle.status = BillingCycleStatus.completed
    cycle.processed_at = now
    for usage in usage_records:
        usage.billed_invoice_id = invoice.id
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.next_billing_at = period_end
    subscription.version += 1
    return invoice


def process_due_billing_cycles(db: Session, *, as_of: datetime | None = None, owner_user_id: int | None = None) -> dict:
    now = as_utc(as_of or utcnow())
    query = (
        select(BillingSubscription)
        .options(
            selectinload(BillingSubscription.plan),
            selectinload(BillingSubscription.pending_plan),
            selectinload(BillingSubscription.customer),
        )
        .where(
            BillingSubscription.status.in_([
                SubscriptionStatus.trial,
                SubscriptionStatus.active,
                SubscriptionStatus.paused,
            ]),
            and_(BillingSubscription.next_billing_at.is_not(None), BillingSubscription.next_billing_at <= now),
        )
        .order_by(BillingSubscription.next_billing_at, BillingSubscription.id)
    )
    if owner_user_id is not None:
        query = query.where(BillingSubscription.owner_user_id == owner_user_id)
    subscriptions = list(db.scalars(query))
    generated: list[int] = []
    skipped = 0
    failures: list[dict] = []
    for subscription in subscriptions:
        try:
            invoice = process_subscription_cycle(db, subscription, as_of=now)
            if invoice:
                generated.append(invoice.id)
            else:
                skipped += 1
        except Exception as exc:
            failures.append({"subscription_id": subscription.id, "error": str(exc)})
    db.commit()
    return {"processed": len(subscriptions), "generated_invoice_ids": generated, "skipped": skipped, "failures": failures, "as_of": now.isoformat()}


def ensure_invoice_pdf(
    db: Session,
    invoice: BillingInvoice,
    *,
    business_name: str,
    business_address: str,
) -> bytes:
    if invoice.pdf_data:
        return invoice.pdf_data
    payload, digest = build_invoice_pdf(invoice, business_name=business_name, business_address=business_address)
    invoice.pdf_data = payload
    invoice.pdf_sha256 = digest
    invoice.pdf_generated_at = utcnow()
    db.flush()
    return payload
