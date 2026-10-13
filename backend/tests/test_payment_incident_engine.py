from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.billing_models import (
    BillingNotification,
    BillingPayment,
    BillingPaymentStatus,
    NotificationPreference,
    PaymentIncident,
    PaymentReconciliation,
    TaskDeadLetter,
)
from app.celery_app import celery_app
from app.core.config import get_settings
from app.database import SessionLocal
from app.services.notification_delivery import (
    deliver_notification_batch,
    notification_claim_statement,
)
from app.services.notification_receipts import sign_notification_receipt
from app.services.payment_incidents import (
    escalate_due_incidents,
    monitor_pending_payments,
    poll_gateway_payments,
)
from app.tasks import record_task_dead_letter


def seed_billing(client):
    response = client.post("/api/v1/billing/demo/seed")
    assert response.status_code == 200, response.text


def test_preferences_queue_all_enabled_channels_and_events_are_durable(authenticated_client):
    seed_billing(authenticated_client)
    customers = authenticated_client.get("/api/v1/billing/customers").json()
    orbit = next(item for item in customers if item["name"] == "Orbit Learning")
    preferences = authenticated_client.get("/api/v1/billing/notification-preferences")
    assert preferences.status_code == 200
    preference = next(item for item in preferences.json() if item["customer_id"] == orbit["id"])
    assert {channel for channel in ("email", "sms", "push") if preference[f"{channel}_enabled"]} == {
        "email",
        "sms",
        "push",
    }
    notifications = authenticated_client.get("/api/v1/billing/notifications").json()
    failure_channels = {
        item["channel"]
        for item in notifications
        if item["customer_id"] == orbit["id"] and item["event_type"] == "payment_failed"
    }
    assert failure_channels == {"email", "sms", "push"}
    events = authenticated_client.get("/api/v1/billing/events").json()
    assert {item["event_type"] for item in events} >= {"payment.failed", "incident.opened", "notification.queued"}


def test_transactional_outbox_delivery_and_signed_receipts(authenticated_client):
    seed_billing(authenticated_client)
    with SessionLocal() as db:
        preferences = list(db.scalars(select(NotificationPreference)))
        for preference in preferences:
            preference.quiet_hours_start = None
            preference.quiet_hours_end = None
        db.commit()
        result = deliver_notification_batch(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))
        assert result["sent"] >= 1
    notifications = authenticated_client.get("/api/v1/billing/notifications").json()
    sent = next(item for item in notifications if item["delivery_status"] == "sent")
    assert sent["attempt_count"] == 1
    assert sent["provider_message_id"].startswith("sandbox_")

    payload = {
        "event_id": f"receipt_{uuid4().hex}",
        "provider_message_id": sent["provider_message_id"],
        "status": "delivered",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"transport": "sandbox-test"},
    }
    signature = sign_notification_receipt(payload, get_settings().notification_receipt_webhook_secret)
    receipt = authenticated_client.post(
        "/api/v1/billing/webhooks/notification-receipts/sandbox",
        json=payload,
        headers={"X-BillFlow-Signature": signature},
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["status"] == "delivered"
    repeated = authenticated_client.post(
        "/api/v1/billing/webhooks/notification-receipts/sandbox",
        json=payload,
        headers={"X-BillFlow-Signature": signature},
    )
    assert repeated.json()["duplicate"] is True


def test_delivery_exhaustion_dead_letters_message_and_opens_incident(authenticated_client, monkeypatch):
    seed_billing(authenticated_client)

    class BrokenAdapter:
        provider = "broken"

        def send(self, _notification):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.services.notification_delivery.adapter_for", lambda *_: BrokenAdapter())
    with SessionLocal() as db:
        item = db.scalar(select(BillingNotification).order_by(BillingNotification.id))
        item.max_attempts = 1
        item.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        preference = db.scalar(
            select(NotificationPreference).where(NotificationPreference.customer_id == item.customer_id)
        )
        preference.quiet_hours_start = None
        preference.quiet_hours_end = None
        db.commit()
        result = deliver_notification_batch(db, batch_size=1)
        assert result["dead_lettered"] == 1
        db.refresh(item)
        assert item.delivery_status == "failed"
        assert item.dead_lettered_at is not None
        incident = db.scalar(
            select(PaymentIncident).where(
                PaymentIncident.dedupe_key == f"notification:{item.id}:delivery_exhausted"
            )
        )
        assert incident and incident.status == "open"


def test_pending_timeout_then_gateway_poll_reconciles_and_resolves(authenticated_client):
    seed_billing(authenticated_client)
    invoices = authenticated_client.get("/api/v1/billing/invoices").json()
    invoice = next(item for item in invoices if item["status"] == "failed")
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        payment = BillingPayment(
            owner_user_id=1,
            invoice_id=invoice["id"],
            status=BillingPaymentStatus.pending,
            amount=invoice["total"],
            currency=invoice["currency"],
            gateway="mock_gateway",
            gateway_event_id=f"pending_{uuid4().hex}",
            gateway_reference=f"mock_{uuid4().hex}",
            idempotency_key=f"pending:{uuid4().hex}",
            provider_status="succeeded",
            processing_state="pending_provider_confirmation",
            created_at=old,
        )
        db.add(payment)
        db.commit()
        payment_id = payment.id
        timeout = monitor_pending_payments(db, now=datetime.now(timezone.utc))
        assert timeout["timed_out"] == 1
        db.refresh(payment)
        assert payment.processing_state == "timed_out"
        result = poll_gateway_payments(db, now=datetime.now(timezone.utc) + timedelta(seconds=1))
        assert result["succeeded"] == 1
        db.refresh(payment)
        assert payment.status == BillingPaymentStatus.succeeded
        assert payment.reconciled_at is not None
        reconciliation = db.scalar(
            select(PaymentReconciliation).where(PaymentReconciliation.payment_id == payment_id)
        )
        assert reconciliation and reconciliation.resolved_status == "succeeded"
        timeout_incident = db.scalar(
            select(PaymentIncident).where(
                PaymentIncident.dedupe_key == f"payment:{payment_id}:confirmation_timeout"
            )
        )
        assert timeout_incident.status == "resolved"


def test_incident_escalation_and_operator_controls(authenticated_client):
    seed_billing(authenticated_client)
    incidents = authenticated_client.get("/api/v1/billing/incidents").json()
    incident = next(item for item in incidents if item["incident_type"] == "payment_failed")
    with SessionLocal() as db:
        result = escalate_due_incidents(
            db,
            now=datetime.fromisoformat(incident["first_detected_at"]) + timedelta(minutes=6),
        )
        assert result["incidents"] == 1
        assert result["notifications_queued"] == 1
    acknowledged = authenticated_client.post(f"/api/v1/billing/incidents/{incident['id']}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    resolved = authenticated_client.post(f"/api/v1/billing/incidents/{incident['id']}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_postgres_claim_uses_skip_locked_and_celery_schedules_watchdogs():
    statement = notification_claim_statement(now=datetime.now(timezone.utc), batch_size=25)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    scheduled_tasks = {item["task"] for item in celery_app.conf.beat_schedule.values()}
    assert {
        "billing.deliver_notifications",
        "billing.monitor_pending_payments",
        "billing.poll_gateway_status",
        "billing.escalate_incidents",
        "billing.monitor_queue_health",
    } <= scheduled_tasks


def test_terminal_celery_failure_is_persisted_once(authenticated_client):
    task_id = f"task_{uuid4().hex}"
    record_task_dead_letter(
        task_id=task_id,
        task_name="billing.test_failure",
        args=("safe-argument",),
        kwargs={"batch": 4},
        exception=RuntimeError("terminal test failure"),
        traceback_text="traceback",
        attempts=6,
    )
    record_task_dead_letter(
        task_id=task_id,
        task_name="billing.test_failure",
        args=(),
        kwargs={},
        exception=RuntimeError("duplicate callback"),
        traceback_text=None,
        attempts=6,
    )
    with SessionLocal() as db:
        rows = list(db.scalars(select(TaskDeadLetter).where(TaskDeadLetter.task_id == task_id)))
        assert len(rows) == 1
        assert rows[0].attempts == 6
        assert rows[0].status == "unresolved"


def test_queue_health_and_prometheus_metrics(authenticated_client):
    seed_billing(authenticated_client)
    health = authenticated_client.get("/api/v1/billing/queue-health")
    assert health.status_code == 200
    assert health.json()["queued_notifications"] >= 2
    metrics = authenticated_client.get("/metrics")
    assert metrics.status_code == 200
    assert "billflow_outbox_queued" in metrics.text
