from sqlalchemy.orm import Session

from app.billing_models import BillingCustomer, BillingInvoice, BillingNotification


def queue_billing_notification(
    db: Session,
    *,
    owner_user_id: int,
    customer: BillingCustomer,
    event_type: str,
    invoice: BillingInvoice | None = None,
    payload: dict | None = None,
) -> BillingNotification:
    notification = BillingNotification(
        owner_user_id=owner_user_id,
        customer_id=customer.id,
        invoice_id=invoice.id if invoice else None,
        event_type=event_type,
        recipient=customer.email,
        channel="email",
        payload=payload or {},
    )
    db.add(notification)
    return notification
