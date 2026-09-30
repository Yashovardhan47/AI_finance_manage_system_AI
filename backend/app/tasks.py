from sqlalchemy import select

from app.billing_models import BillingNotification, NotificationStatus
from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.billing_engine import run_due_retries
from app.services.billing_utils import utcnow
from app.services.invoicing import process_due_billing_cycles


@celery_app.task(name="billing.process_due_cycles")
def process_due_cycles_task() -> dict:
    with SessionLocal() as db:
        return process_due_billing_cycles(db)


@celery_app.task(name="billing.process_due_retries")
def process_due_retries_task() -> dict:
    with SessionLocal() as db:
        return run_due_retries(db)


@celery_app.task(name="billing.deliver_notifications")
def deliver_notifications_task() -> dict:
    """Drain the durable notification outbox.

    The default adapter records successful sandbox delivery. Production can
    replace this task body with SES, SendGrid, SMTP, or another approved provider
    without changing billing transactions or webhook processing.
    """
    with SessionLocal() as db:
        items = list(
            db.scalars(
                select(BillingNotification)
                .where(BillingNotification.status == NotificationStatus.queued)
                .order_by(BillingNotification.created_at)
                .limit(100)
            )
        )
        now = utcnow()
        for item in items:
            item.status = NotificationStatus.sent
            item.sent_at = now
        db.commit()
        return {"delivered": len(items), "adapter": "sandbox_outbox"}
