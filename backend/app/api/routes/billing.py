from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.billing_models import (
    BillingCustomer,
    BillingInvoice,
    BillingNotification,
    BillingPlan,
    BillingRefund,
    BillingSubscription,
    InvoiceStatus,
    PaymentRetry,
    TaxRate,
    UsageRecord,
)
from app.billing_schemas import (
    CancelRequest,
    CustomerCreate,
    CustomerUpdate,
    CycleRunRequest,
    GatewayWebhookPayload,
    MockChargeRequest,
    PauseRequest,
    PlanChangeRequest,
    PlanCreate,
    PlanUpdate,
    RefundRequest,
    RetryRunRequest,
    SubscriptionCreate,
    TaxRateCreate,
    TaxRateUpdate,
    UsageCreate,
)
from app.core.config import get_settings
from app.core.security import get_current_user
from app.database import get_db
from app.models import AuditLog, User
from app.services.audit import write_audit
from app.services.billing_demo import seed_billing_demo
from app.services.billing_engine import (
    billing_dashboard,
    issue_refund,
    process_gateway_event,
    run_due_retries,
    simulate_gateway_charge,
    tax_summary,
)
from app.services.billing_utils import utcnow
from app.services.invoicing import ensure_invoice_pdf, process_due_billing_cycles
from app.services.subscription_state import InvalidSubscriptionTransition, status_timeline
from app.services.subscriptions import (
    cancel_subscription,
    change_subscription_plan,
    create_subscription,
    pause_subscription,
    resume_subscription,
)


router = APIRouter(prefix="/billing", tags=["billing operations"])
settings = get_settings()


@router.post("/demo/seed")
def seed_demo(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return seed_billing_demo(db, owner_user_id=user.id)


@router.get("/plans")
def list_plans(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(BillingPlan).where(BillingPlan.owner_user_id == user.id)
    if not include_archived:
        query = query.where(BillingPlan.is_archived.is_(False))
    return [_plan_dict(item) for item in db.scalars(query.order_by(BillingPlan.price, BillingPlan.id))]


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    plan = BillingPlan(owner_user_id=user.id, **payload.model_dump())
    db.add(plan)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A plan with this code already exists") from exc
    write_audit(db, user_id=user.id, action="billing.plan.created", entity_type="billing_plan", entity_id=plan.id, detail={"code": plan.code, "price": str(plan.price)})
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, payload: PlanUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    plan = _owned_plan(db, user.id, plan_id, include_archived=True)
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(plan, key, value)
    write_audit(db, user_id=user.id, action="billing.plan.updated", entity_type="billing_plan", entity_id=plan.id, detail={key: str(value) for key, value in changes.items()})
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


@router.post("/plans/{plan_id}/archive")
def archive_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    plan = _owned_plan(db, user.id, plan_id, include_archived=True)
    plan.is_archived = True
    plan.archived_at = utcnow()
    write_audit(db, user_id=user.id, action="billing.plan.archived", entity_type="billing_plan", entity_id=plan.id, detail={"code": plan.code})
    db.commit()
    return _plan_dict(plan)


@router.get("/customers")
def list_customers(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    customers = db.scalars(select(BillingCustomer).where(BillingCustomer.owner_user_id == user.id).order_by(BillingCustomer.name))
    return [_customer_dict(item) for item in customers]


@router.post("/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    data = payload.model_dump()
    metadata_json = data.pop("metadata")
    customer = BillingCustomer(owner_user_id=user.id, metadata_json=metadata_json, **data)
    db.add(customer)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A customer with this external key already exists") from exc
    write_audit(db, user_id=user.id, action="billing.customer.created", entity_type="billing_customer", entity_id=customer.id, detail={"customer_id": customer.id, "external_key": customer.external_key})
    db.commit()
    db.refresh(customer)
    return _customer_dict(customer)


@router.patch("/customers/{customer_id}")
def update_customer(customer_id: int, payload: CustomerUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    customer = _owned_customer(db, user.id, customer_id)
    changes = payload.model_dump(exclude_none=True)
    if "metadata" in changes:
        changes["metadata_json"] = changes.pop("metadata")
    if "country_code" in changes:
        changes["country_code"] = changes["country_code"].upper()
    for key, value in changes.items():
        setattr(customer, key, value)
    write_audit(db, user_id=user.id, action="billing.customer.updated", entity_type="billing_customer", entity_id=customer.id, detail={"customer_id": customer.id, "fields": sorted(changes)})
    db.commit()
    db.refresh(customer)
    return _customer_dict(customer)


@router.get("/subscriptions")
def list_subscriptions(
    subscription_status: str | None = Query(default=None, alias="status"),
    customer_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = (
        select(BillingSubscription)
        .options(
            selectinload(BillingSubscription.customer),
            selectinload(BillingSubscription.plan),
            selectinload(BillingSubscription.pending_plan),
        )
        .where(BillingSubscription.owner_user_id == user.id)
    )
    if subscription_status:
        query = query.where(BillingSubscription.status == subscription_status)
    if customer_id:
        query = query.where(BillingSubscription.customer_id == customer_id)
    return [_subscription_dict(item) for item in db.scalars(query.order_by(BillingSubscription.created_at.desc()))]


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def create_customer_subscription(
    payload: SubscriptionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    customer = _owned_customer(db, user.id, payload.customer_id)
    plan = _owned_plan(db, user.id, payload.plan_id)
    subscription = create_subscription(
        db,
        owner_user_id=user.id,
        customer=customer,
        plan=plan,
        quantity=payload.quantity,
        start_trial=payload.start_trial,
        start_at=payload.start_at,
    )
    db.commit()
    db.refresh(subscription)
    subscription.customer = customer
    subscription.plan = plan
    return _subscription_dict(subscription)


@router.post("/subscriptions/{subscription_id}/change-plan")
def change_plan(
    subscription_id: int,
    payload: PlanChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    subscription = _owned_subscription(db, user.id, subscription_id)
    new_plan = _owned_plan(db, user.id, payload.plan_id)
    try:
        invoice, quote = change_subscription_plan(db, subscription=subscription, new_plan=new_plan, timing=payload.timing)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"subscription": _subscription_dict(subscription), "timing": payload.timing, "proration": quote, "invoice": _invoice_dict(invoice) if invoice else None}


@router.post("/subscriptions/{subscription_id}/pause")
def pause(
    subscription_id: int,
    payload: PauseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    subscription = _owned_subscription(db, user.id, subscription_id)
    try:
        pause_subscription(db, subscription=subscription, resume_at=payload.resume_at)
    except InvalidSubscriptionTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _subscription_dict(subscription)


@router.post("/subscriptions/{subscription_id}/resume")
def resume(subscription_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    subscription = _owned_subscription(db, user.id, subscription_id)
    try:
        resume_subscription(db, subscription=subscription)
    except InvalidSubscriptionTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _subscription_dict(subscription)


@router.post("/subscriptions/{subscription_id}/cancel")
def cancel(
    subscription_id: int,
    payload: CancelRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    subscription = _owned_subscription(db, user.id, subscription_id)
    try:
        subscription, refund_id = cancel_subscription(
            db,
            subscription=subscription,
            timing=payload.timing,
            refund_unused=payload.refund_unused,
            reason=payload.reason,
        )
    except (InvalidSubscriptionTransition, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"subscription": _subscription_dict(subscription), "refund_id": refund_id}


@router.post("/usage", status_code=status.HTTP_201_CREATED)
def record_usage(payload: UsageCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    subscription = _owned_subscription(db, user.id, payload.subscription_id)
    existing = db.scalar(
        select(UsageRecord).where(
            UsageRecord.owner_user_id == user.id,
            UsageRecord.idempotency_key == payload.idempotency_key,
        )
    )
    if existing:
        return _usage_dict(existing)
    usage = UsageRecord(
        owner_user_id=user.id,
        subscription_id=subscription.id,
        metric=payload.metric,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        idempotency_key=payload.idempotency_key,
        occurred_at=payload.occurred_at or utcnow(),
    )
    db.add(usage)
    db.flush()
    write_audit(db, user_id=user.id, action="billing.usage.recorded", entity_type="usage_record", entity_id=usage.id, detail={"customer_id": subscription.customer_id, "subscription_id": subscription.id, "metric": usage.metric, "quantity": str(usage.quantity)})
    db.commit()
    return _usage_dict(usage)


@router.post("/cycles/run")
def run_cycles(payload: CycleRunRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return process_due_billing_cycles(db, as_of=payload.as_of, owner_user_id=user.id)


@router.get("/invoices")
def list_invoices(
    invoice_status: str | None = Query(default=None, alias="status"),
    customer_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = (
        select(BillingInvoice)
        .options(
            selectinload(BillingInvoice.customer),
            selectinload(BillingInvoice.subscription).selectinload(BillingSubscription.plan),
            selectinload(BillingInvoice.line_items),
        )
        .where(BillingInvoice.owner_user_id == user.id)
    )
    if invoice_status:
        query = query.where(BillingInvoice.status == invoice_status)
    if customer_id:
        query = query.where(BillingInvoice.customer_id == customer_id)
    return [_invoice_dict(item) for item in db.scalars(query.order_by(BillingInvoice.created_at.desc()))]


@router.get("/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _invoice_dict(_owned_invoice(db, user.id, invoice_id))


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    invoice = _owned_invoice(db, user.id, invoice_id)
    payload = ensure_invoice_pdf(
        db,
        invoice,
        business_name=settings.invoice_business_name,
        business_address=settings.invoice_business_address,
    )
    db.commit()
    return Response(
        payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"', "ETag": invoice.pdf_sha256 or ""},
    )


@router.post("/mock-gateway/charge")
def mock_gateway_charge(
    payload: MockChargeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    invoice = _owned_invoice(db, user.id, payload.invoice_id)
    if invoice.status in {InvoiceStatus.paid, InvoiceStatus.refunded, InvoiceStatus.void}:
        raise HTTPException(status_code=409, detail=f"Invoice cannot be charged while {invoice.status.value}")
    try:
        result = simulate_gateway_charge(
            db,
            invoice=invoice,
            idempotency_key=payload.idempotency_key,
            outcome=payload.outcome,
            failure_reason=payload.failure_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/webhooks/mock-gateway")
def mock_gateway_webhook(
    payload: GatewayWebhookPayload,
    x_billflow_signature: str | None = Header(default=None, alias="X-BillFlow-Signature"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = process_gateway_event(
            db,
            payload=payload.model_dump(mode="json"),
            signature=x_billflow_signature,
            require_signature=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/invoices/{invoice_id}/refund", status_code=status.HTTP_201_CREATED)
def refund_invoice(
    invoice_id: int,
    payload: RefundRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    invoice = _owned_invoice(db, user.id, invoice_id)
    try:
        refund = issue_refund(db, invoice=invoice, amount=payload.amount, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _refund_dict(refund)


@router.get("/retries")
def list_retries(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    retries = db.scalars(
        select(PaymentRetry)
        .options(selectinload(PaymentRetry.invoice))
        .where(PaymentRetry.owner_user_id == user.id)
        .order_by(PaymentRetry.scheduled_for, PaymentRetry.attempt_number)
    )
    return [_retry_dict(item) for item in retries]


@router.post("/retries/run")
def run_retries(payload: RetryRunRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return run_due_retries(db, as_of=payload.as_of, owner_user_id=user.id, forced_outcome=payload.forced_outcome)


@router.get("/tax-rates")
def list_tax_rates(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    rates = db.scalars(select(TaxRate).where(TaxRate.owner_user_id == user.id).order_by(TaxRate.country_code, TaxRate.region, TaxRate.name))
    return [_tax_rate_dict(item) for item in rates]


@router.post("/tax-rates", status_code=status.HTTP_201_CREATED)
def create_tax_rate(payload: TaxRateCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rate = TaxRate(owner_user_id=user.id, **payload.model_dump())
    db.add(rate)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A tax rate with this scope and name already exists") from exc
    write_audit(db, user_id=user.id, action="billing.tax_rate.created", entity_type="tax_rate", entity_id=rate.id, detail={"country_code": rate.country_code, "region": rate.region, "rate_percent": str(rate.rate_percent)})
    db.commit()
    return _tax_rate_dict(rate)


@router.patch("/tax-rates/{rate_id}")
def update_tax_rate(rate_id: int, payload: TaxRateUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rate = db.scalar(select(TaxRate).where(TaxRate.id == rate_id, TaxRate.owner_user_id == user.id))
    if not rate:
        raise HTTPException(status_code=404, detail="Tax rate not found")
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(rate, key, value)
    write_audit(db, user_id=user.id, action="billing.tax_rate.updated", entity_type="tax_rate", entity_id=rate.id, detail={key: str(value) for key, value in changes.items()})
    db.commit()
    return _tax_rate_dict(rate)


@router.get("/tax-summary")
def get_tax_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return tax_summary(db, owner_user_id=user.id, start=start, end=end)


@router.get("/dashboard")
def dashboard(
    months: int = Query(default=12, ge=1, le=36),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return billing_dashboard(db, owner_user_id=user.id, months=months)


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    items = db.scalars(
        select(BillingNotification)
        .where(BillingNotification.owner_user_id == user.id)
        .order_by(BillingNotification.created_at.desc())
        .limit(100)
    )
    return [{"id": item.id, "customer_id": item.customer_id, "invoice_id": item.invoice_id, "event_type": item.event_type, "recipient": item.recipient, "channel": item.channel, "status": item.status.value, "payload": item.payload, "failure_reason": item.failure_reason, "sent_at": item.sent_at.isoformat() if item.sent_at else None, "created_at": item.created_at.isoformat()} for item in items]


@router.get("/audit")
def billing_audit(
    customer_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == user.id, AuditLog.action.like("billing.%"))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    )
    if customer_id is not None:
        items = [item for item in items if str((item.detail or {}).get("customer_id")) == str(customer_id)]
    return [{"id": item.id, "action": item.action, "entity_type": item.entity_type, "entity_id": item.entity_id, "detail": item.detail, "created_at": item.created_at.isoformat()} for item in items]


def _owned_plan(db: Session, owner_user_id: int, plan_id: int, include_archived: bool = False) -> BillingPlan:
    query = select(BillingPlan).where(BillingPlan.id == plan_id, BillingPlan.owner_user_id == owner_user_id)
    if not include_archived:
        query = query.where(BillingPlan.is_archived.is_(False))
    plan = db.scalar(query)
    if not plan:
        raise HTTPException(status_code=404, detail="Billing plan not found")
    return plan


def _owned_customer(db: Session, owner_user_id: int, customer_id: int) -> BillingCustomer:
    customer = db.scalar(select(BillingCustomer).where(BillingCustomer.id == customer_id, BillingCustomer.owner_user_id == owner_user_id))
    if not customer:
        raise HTTPException(status_code=404, detail="Billing customer not found")
    return customer


def _owned_subscription(db: Session, owner_user_id: int, subscription_id: int) -> BillingSubscription:
    subscription = db.scalar(
        select(BillingSubscription)
        .options(
            selectinload(BillingSubscription.customer),
            selectinload(BillingSubscription.plan),
            selectinload(BillingSubscription.pending_plan),
        )
        .where(BillingSubscription.id == subscription_id, BillingSubscription.owner_user_id == owner_user_id)
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription


def _owned_invoice(db: Session, owner_user_id: int, invoice_id: int) -> BillingInvoice:
    invoice = db.scalar(
        select(BillingInvoice)
        .options(
            selectinload(BillingInvoice.customer),
            selectinload(BillingInvoice.subscription).selectinload(BillingSubscription.plan),
            selectinload(BillingInvoice.line_items),
            selectinload(BillingInvoice.payments),
            selectinload(BillingInvoice.refunds),
            selectinload(BillingInvoice.retries),
        )
        .where(BillingInvoice.id == invoice_id, BillingInvoice.owner_user_id == owner_user_id)
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _plan_dict(item: BillingPlan) -> dict:
    return {"id": item.id, "code": item.code, "name": item.name, "description": item.description, "price": float(item.price), "currency": item.currency, "billing_interval": item.billing_interval.value, "feature_entitlements": item.feature_entitlements, "trial_days": item.trial_days, "is_archived": item.is_archived, "archived_at": item.archived_at.isoformat() if item.archived_at else None, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


def _customer_dict(item: BillingCustomer) -> dict:
    return {"id": item.id, "external_key": item.external_key, "name": item.name, "email": item.email, "country_code": item.country_code, "region": item.region, "tax_id": item.tax_id, "credit_balance": float(item.credit_balance), "billing_address": item.billing_address, "metadata": item.metadata_json, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


def _subscription_dict(item: BillingSubscription) -> dict:
    return {"id": item.id, "customer_id": item.customer_id, "customer_name": item.customer.name, "plan_id": item.plan_id, "plan_name": item.plan.name, "pending_plan_id": item.pending_plan_id, "pending_plan_name": item.pending_plan.name if item.pending_plan else None, "status": item.status.value, "quantity": item.quantity, "timeline": status_timeline(item), "trial_ends_at": item.trial_ends_at.isoformat() if item.trial_ends_at else None, "resumes_at": item.resumes_at.isoformat() if item.resumes_at else None, "current_period_start": item.current_period_start.isoformat(), "current_period_end": item.current_period_end.isoformat(), "next_billing_at": item.next_billing_at.isoformat() if item.next_billing_at else None, "cancel_at_period_end": item.cancel_at_period_end, "cancellation_reason": item.cancellation_reason, "version": item.version, "created_at": item.created_at.isoformat()}


def _invoice_dict(item: BillingInvoice | None) -> dict | None:
    if item is None:
        return None
    return {"id": item.id, "invoice_number": item.invoice_number, "customer_id": item.customer_id, "customer_name": item.customer.name, "subscription_id": item.subscription_id, "plan_name": item.subscription.plan.name, "status": item.status.value, "currency": item.currency, "subtotal": float(item.subtotal), "proration_total": float(item.proration_total), "usage_total": float(item.usage_total), "tax_total": float(item.tax_total), "total": float(item.total), "amount_paid": float(item.amount_paid), "amount_refunded": float(item.amount_refunded), "issue_date": item.issue_date.isoformat(), "due_date": item.due_date.isoformat(), "period_start": item.period_start.isoformat(), "period_end": item.period_end.isoformat(), "payment_terms": item.payment_terms, "pdf_available": bool(item.pdf_data), "pdf_sha256": item.pdf_sha256, "line_items": [{"id": line.id, "line_type": line.line_type.value, "description": line.description, "quantity": float(line.quantity), "unit_amount": float(line.unit_amount), "amount": float(line.amount), "tax_rate_percent": float(line.tax_rate_percent) if line.tax_rate_percent is not None else None, "metadata": line.metadata_json} for line in item.line_items], "created_at": item.created_at.isoformat()}


def _usage_dict(item: UsageRecord) -> dict:
    return {"id": item.id, "subscription_id": item.subscription_id, "billed_invoice_id": item.billed_invoice_id, "metric": item.metric, "quantity": float(item.quantity), "unit_price": float(item.unit_price), "idempotency_key": item.idempotency_key, "occurred_at": item.occurred_at.isoformat(), "created_at": item.created_at.isoformat()}


def _retry_dict(item: PaymentRetry) -> dict:
    return {"id": item.id, "invoice_id": item.invoice_id, "invoice_number": item.invoice.invoice_number, "subscription_id": item.subscription_id, "attempt_number": item.attempt_number, "scheduled_for": item.scheduled_for.isoformat(), "status": item.status.value, "last_error": item.last_error, "processed_at": item.processed_at.isoformat() if item.processed_at else None}


def _refund_dict(item: BillingRefund) -> dict:
    return {"id": item.id, "invoice_id": item.invoice_id, "payment_id": item.payment_id, "amount": float(item.amount), "reason": item.reason, "status": item.status.value, "gateway_reference": item.gateway_reference, "created_at": item.created_at.isoformat(), "processed_at": item.processed_at.isoformat() if item.processed_at else None}


def _tax_rate_dict(item: TaxRate) -> dict:
    return {"id": item.id, "name": item.name, "country_code": item.country_code, "region": item.region, "rate_percent": float(item.rate_percent), "is_active": item.is_active, "effective_from": item.effective_from.isoformat(), "effective_to": item.effective_to.isoformat() if item.effective_to else None, "created_at": item.created_at.isoformat()}
