from __future__ import annotations

import json

from celery import Task
from sqlalchemy.exc import IntegrityError

from app.billing_models import TaskDeadLetter
from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.billing_engine import run_due_retries
from app.services.invoicing import process_due_billing_cycles
from app.services.notification_delivery import deliver_notification_batch
from app.services.payment_incidents import (
    escalate_due_incidents,
    monitor_pending_payments,
    monitor_queue_health,
    poll_gateway_payments,
)


class ReliableBillingTask(Task):
    """Retry transient task failures, then persist the terminal envelope."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    retry_kwargs = {"max_retries": 5}
    acks_late = True
    reject_on_worker_lost = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        try:
            record_task_dead_letter(
                task_id=task_id,
                task_name=self.name,
                args=args,
                kwargs=kwargs,
                exception=exc,
                traceback_text=str(einfo) if einfo else None,
                attempts=int(getattr(self.request, "retries", 0)) + 1,
            )
        finally:
            super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(base=ReliableBillingTask, name="billing.process_due_cycles")
def process_due_cycles_task() -> dict:
    with SessionLocal() as db:
        return process_due_billing_cycles(db)


@celery_app.task(base=ReliableBillingTask, name="billing.process_due_retries")
def process_due_retries_task() -> dict:
    with SessionLocal() as db:
        return run_due_retries(db)


@celery_app.task(base=ReliableBillingTask, name="billing.deliver_notifications")
def deliver_notifications_task() -> dict:
    with SessionLocal() as db:
        return deliver_notification_batch(db)


@celery_app.task(base=ReliableBillingTask, name="billing.monitor_pending_payments")
def monitor_pending_payments_task() -> dict:
    with SessionLocal() as db:
        return monitor_pending_payments(db)


@celery_app.task(base=ReliableBillingTask, name="billing.poll_gateway_status")
def poll_gateway_status_task() -> dict:
    with SessionLocal() as db:
        return poll_gateway_payments(db)


@celery_app.task(base=ReliableBillingTask, name="billing.escalate_incidents")
def escalate_incidents_task() -> dict:
    with SessionLocal() as db:
        return escalate_due_incidents(db)


@celery_app.task(base=ReliableBillingTask, name="billing.monitor_queue_health")
def monitor_queue_health_task() -> dict:
    with SessionLocal() as db:
        return monitor_queue_health(db)


def _safe_json(value):
    return json.loads(json.dumps(value, default=str))


def record_task_dead_letter(
    *,
    task_id: str,
    task_name: str,
    args,
    kwargs,
    exception: Exception,
    traceback_text: str | None,
    attempts: int,
) -> None:
    with SessionLocal() as db:
        db.add(
            TaskDeadLetter(
                task_id=task_id,
                task_name=task_name,
                args=_safe_json(args),
                kwargs=_safe_json(kwargs),
                exception_type=type(exception).__name__,
                exception_message=str(exception)[:4000],
                traceback_text=traceback_text[:12000] if traceback_text else None,
                attempts=attempts,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
