from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing_models import (
    BillingCustomer,
    BillingInterval,
    BillingPlan,
    BillingSubscription,
    InvoiceLineType,
    InvoiceStatus,
    SubscriptionStatus,
    TaxRate,
)
from app.services.audit import write_audit
from app.services.billing_engine import simulate_gateway_charge
from app.services.billing_utils import add_billing_period, money, utcnow
from app.services.invoicing import create_invoice, process_subscription_cycle
from app.services.subscription_state import transition_subscription
from app.services.subscriptions import create_subscription


def seed_billing_demo(db: Session, *, owner_user_id: int) -> dict:
    existing = db.scalar(select(BillingPlan.id).where(BillingPlan.owner_user_id == owner_user_id).limit(1))
    if existing:
        return {"seeded": False, "message": "Billing Operations demo data already exists"}

    now = utcnow()
    tax = TaxRate(
        owner_user_id=owner_user_id,
        name="India GST",
        country_code="IN",
        region=None,
        rate_percent=Decimal("18.00"),
        effective_from=date(now.year - 1, 1, 1),
    )
    plans = [
        BillingPlan(owner_user_id=owner_user_id, code="starter", name="Starter", description="Core billing for early teams", price=Decimal("999"), currency="INR", billing_interval=BillingInterval.monthly, trial_days=14, feature_entitlements={"seats": 5, "projects": 20, "support": "email"}),
        BillingPlan(owner_user_id=owner_user_id, code="growth", name="Growth", description="Automation and analytics for scaling teams", price=Decimal("2999"), currency="INR", billing_interval=BillingInterval.monthly, trial_days=14, feature_entitlements={"seats": 25, "projects": "unlimited", "support": "priority"}),
        BillingPlan(owner_user_id=owner_user_id, code="scale-annual", name="Scale Annual", description="Annual enterprise operations plan", price=Decimal("29999"), currency="INR", billing_interval=BillingInterval.annual, trial_days=30, feature_entitlements={"seats": 100, "sso": True, "support": "dedicated"}),
    ]
    customers = [
        BillingCustomer(owner_user_id=owner_user_id, external_key="CUST-ACME", name="Acme Analytics", email="billing@acme.demo", country_code="IN", region="Karnataka", tax_id="GSTIN-DEMO-001", billing_address={"line1": "100 Innovation Road", "city": "Bengaluru", "postal_code": "560001", "country": "India"}),
        BillingCustomer(owner_user_id=owner_user_id, external_key="CUST-NOVA", name="Nova Health", email="finance@nova.demo", country_code="IN", region="Telangana", tax_id="GSTIN-DEMO-002", billing_address={"line1": "22 Health Park", "city": "Hyderabad", "postal_code": "500001", "country": "India"}),
        BillingCustomer(owner_user_id=owner_user_id, external_key="CUST-ORBIT", name="Orbit Learning", email="accounts@orbit.demo", country_code="IN", region="Andhra Pradesh", tax_id="GSTIN-DEMO-003", billing_address={"line1": "7 Campus Avenue", "city": "Tirupati", "postal_code": "517501", "country": "India"}),
        BillingCustomer(owner_user_id=owner_user_id, external_key="CUST-PIXEL", name="Pixel Studio", email="owner@pixel.demo", country_code="IN", region="Maharashtra", tax_id="GSTIN-DEMO-004", billing_address={"line1": "41 Design Street", "city": "Pune", "postal_code": "411001", "country": "India"}),
    ]
    db.add(tax)
    db.add_all(plans + customers)
    db.flush()

    active = create_subscription(db, owner_user_id=owner_user_id, customer=customers[0], plan=plans[1], quantity=1, start_trial=False, start_at=now)
    trial = create_subscription(db, owner_user_id=owner_user_id, customer=customers[1], plan=plans[0], quantity=1, start_trial=True, start_at=now)
    failing = create_subscription(db, owner_user_id=owner_user_id, customer=customers[2], plan=plans[2], quantity=1, start_trial=False, start_at=now)
    cancelled = create_subscription(db, owner_user_id=owner_user_id, customer=customers[3], plan=plans[0], quantity=1, start_trial=False, start_at=now)

    active_invoice = process_subscription_cycle(db, active, as_of=now)
    failing_invoice = process_subscription_cycle(db, failing, as_of=now)
    cancelled_invoice = process_subscription_cycle(db, cancelled, as_of=now)
    assert active_invoice and failing_invoice and cancelled_invoice
    simulate_gateway_charge(db, invoice=active_invoice, idempotency_key="demo-active-payment", outcome="success")
    simulate_gateway_charge(db, invoice=failing_invoice, idempotency_key="demo-failed-payment", outcome="failure")
    simulate_gateway_charge(db, invoice=cancelled_invoice, idempotency_key="demo-cancelled-payment", outcome="success")
    transition_subscription(cancelled, SubscriptionStatus.cancelled, at=now, reason="Demo customer churn")

    for months_ago in range(1, 6):
        period_start = now - timedelta(days=30 * months_ago)
        period_end = add_billing_period(period_start, plans[1].billing_interval)
        invoice = create_invoice(
            db,
            subscription=active,
            period_start=period_start,
            period_end=period_end,
            issue_at=period_start,
            line_specs=[{
                "line_type": InvoiceLineType.plan_fee,
                "description": f"{plans[1].name} historical cycle",
                "quantity": 1,
                "unit_amount": plans[1].price,
                "amount": plans[1].price,
                "metadata": {"plan_id": plans[1].id, "demo_history": True},
            }],
        )
        invoice.status = InvoiceStatus.paid
        invoice.amount_paid = money(invoice.total)
        invoice.paid_at = period_start + timedelta(days=1)

    write_audit(
        db,
        user_id=owner_user_id,
        action="billing.demo.seeded",
        entity_type="billing_workspace",
        detail={"plans": len(plans), "customers": len(customers), "subscriptions": 4},
    )
    db.commit()
    return {
        "seeded": True,
        "message": "Billing Operations demo data is ready",
        "counts": {"plans": len(plans), "customers": len(customers), "subscriptions": 4, "invoices": 8},
        "highlights": {"active_subscription_id": active.id, "trial_subscription_id": trial.id, "past_due_subscription_id": failing.id, "cancelled_subscription_id": cancelled.id},
    }
