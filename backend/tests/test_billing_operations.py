from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.billing_schemas import GatewayWebhookPayload
from app.core.config import get_settings
from app.services.billing_engine import sign_webhook


def seed_billing(client):
    response = client.post("/api/v1/billing/demo/seed")
    assert response.status_code == 200, response.text
    return response.json()


def test_plan_customer_trial_activation_and_lifecycle(authenticated_client):
    plan = authenticated_client.post(
        "/api/v1/billing/plans",
        json={
            "code": "qa-monthly",
            "name": "QA Monthly",
            "price": 1500,
            "currency": "INR",
            "billing_interval": "monthly",
            "feature_entitlements": {"seats": 10},
            "trial_days": 2,
        },
    )
    assert plan.status_code == 201, plan.text
    customer = authenticated_client.post(
        "/api/v1/billing/customers",
        json={"external_key": "QA-CUST-1", "name": "QA Customer", "email": "qa@example.com", "country_code": "IN"},
    )
    assert customer.status_code == 201, customer.text
    subscription = authenticated_client.post(
        "/api/v1/billing/subscriptions",
        json={"customer_id": customer.json()["id"], "plan_id": plan.json()["id"], "start_trial": True},
    )
    assert subscription.status_code == 201, subscription.text
    assert subscription.json()["status"] == "trial"
    trial_end = datetime.fromisoformat(subscription.json()["trial_ends_at"])
    run = authenticated_client.post(
        "/api/v1/billing/cycles/run", json={"as_of": (trial_end + timedelta(minutes=1)).isoformat()}
    )
    assert run.status_code == 200, run.text
    assert len(run.json()["generated_invoice_ids"]) == 1
    current = authenticated_client.get("/api/v1/billing/subscriptions").json()[0]
    assert current["status"] == "active"
    paused = authenticated_client.post(f"/api/v1/billing/subscriptions/{current['id']}/pause", json={})
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    resumed = authenticated_client.post(f"/api/v1/billing/subscriptions/{current['id']}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"


def test_immediate_plan_change_generates_proration_invoice(authenticated_client):
    seed_billing(authenticated_client)
    subscriptions = authenticated_client.get("/api/v1/billing/subscriptions").json()
    active = next(item for item in subscriptions if item["customer_name"] == "Acme Analytics")
    starter = next(item for item in authenticated_client.get("/api/v1/billing/plans").json() if item["code"] == "starter")
    response = authenticated_client.post(
        f"/api/v1/billing/subscriptions/{active['id']}/change-plan",
        json={"plan_id": starter["id"], "timing": "immediate"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["proration"]["fraction_remaining"] > 0.9
    assert {item["line_type"] for item in data["invoice"]["line_items"]} >= {"proration_credit", "proration_debit"}
    assert data["subscription"]["plan_id"] == starter["id"]


def test_end_of_cycle_plan_change_and_cancellation_are_scheduled(authenticated_client):
    seed_billing(authenticated_client)
    subscriptions = authenticated_client.get("/api/v1/billing/subscriptions").json()
    trial = next(item for item in subscriptions if item["status"] == "trial")
    growth = next(item for item in authenticated_client.get("/api/v1/billing/plans").json() if item["code"] == "growth")
    change = authenticated_client.post(
        f"/api/v1/billing/subscriptions/{trial['id']}/change-plan",
        json={"plan_id": growth["id"], "timing": "end_of_cycle"},
    )
    assert change.status_code == 200
    assert change.json()["subscription"]["pending_plan_id"] == growth["id"]
    cancel = authenticated_client.post(
        f"/api/v1/billing/subscriptions/{trial['id']}/cancel",
        json={"timing": "end_of_cycle", "refund_unused": False, "reason": "End after evaluation"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["subscription"]["cancel_at_period_end"] is True


def test_usage_tax_invoice_and_pdf_export(authenticated_client):
    seed_billing(authenticated_client)
    subscription = next(
        item for item in authenticated_client.get("/api/v1/billing/subscriptions").json() if item["customer_name"] == "Acme Analytics"
    )
    usage = authenticated_client.post(
        "/api/v1/billing/usage",
        json={"subscription_id": subscription["id"], "metric": "api_calls", "quantity": 2500, "unit_price": 0.2, "idempotency_key": "usage-acme-001"},
    )
    assert usage.status_code == 201, usage.text
    as_of = datetime.fromisoformat(subscription["current_period_end"]) + timedelta(minutes=1)
    cycle = authenticated_client.post("/api/v1/billing/cycles/run", json={"as_of": as_of.isoformat()})
    assert cycle.status_code == 200
    generated = [
        authenticated_client.get(f"/api/v1/billing/invoices/{invoice_id}").json()
        for invoice_id in cycle.json()["generated_invoice_ids"]
    ]
    invoice = next(item for item in generated if item["subscription_id"] == subscription["id"])
    invoice_id = invoice["id"]
    assert invoice["usage_total"] == 500.0
    assert invoice["tax_total"] > 0
    assert any(item["line_type"] == "tax" for item in invoice["line_items"])
    pdf = authenticated_client.get(f"/api/v1/billing/invoices/{invoice_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 1500


def test_mock_gateway_failure_schedules_three_retries_and_marks_past_due(authenticated_client):
    seed_billing(authenticated_client)
    invoices = authenticated_client.get("/api/v1/billing/invoices").json()
    failed = next(item for item in invoices if item["status"] == "failed")
    retries = [item for item in authenticated_client.get("/api/v1/billing/retries").json() if item["invoice_id"] == failed["id"]]
    assert [item["attempt_number"] for item in retries] == [1, 2, 3]
    assert all(item["status"] == "queued" for item in retries)
    subscription = next(item for item in authenticated_client.get("/api/v1/billing/subscriptions").json() if item["id"] == failed["subscription_id"])
    assert subscription["status"] == "past_due"


def test_retry_success_recovers_subscription_and_cancels_later_attempts(authenticated_client):
    seed_billing(authenticated_client)
    failed = next(item for item in authenticated_client.get("/api/v1/billing/invoices").json() if item["status"] == "failed")
    retries = [item for item in authenticated_client.get("/api/v1/billing/retries").json() if item["invoice_id"] == failed["id"]]
    first_due = datetime.fromisoformat(retries[0]["scheduled_for"]) + timedelta(seconds=1)
    run = authenticated_client.post(
        "/api/v1/billing/retries/run",
        json={"as_of": first_due.isoformat(), "forced_outcome": "success"},
    )
    assert run.status_code == 200, run.text
    assert run.json()["processed"] == 1
    invoice = authenticated_client.get(f"/api/v1/billing/invoices/{failed['id']}").json()
    assert invoice["status"] == "paid"
    current_retries = [item for item in authenticated_client.get("/api/v1/billing/retries").json() if item["invoice_id"] == failed["id"]]
    assert current_retries[0]["status"] == "succeeded"
    assert all(item["status"] == "cancelled" for item in current_retries[1:])
    subscription = next(item for item in authenticated_client.get("/api/v1/billing/subscriptions").json() if item["id"] == failed["subscription_id"])
    assert subscription["status"] == "active"


def test_retry_exhaustion_cancels_subscription(authenticated_client):
    seed_billing(authenticated_client)
    failed = next(item for item in authenticated_client.get("/api/v1/billing/invoices").json() if item["status"] == "failed")
    retries = [item for item in authenticated_client.get("/api/v1/billing/retries").json() if item["invoice_id"] == failed["id"]]
    last_due = datetime.fromisoformat(retries[-1]["scheduled_for"]) + timedelta(seconds=1)
    run = authenticated_client.post(
        "/api/v1/billing/retries/run",
        json={"as_of": last_due.isoformat(), "forced_outcome": "failure"},
    )
    assert run.status_code == 200, run.text
    assert run.json()["processed"] == 3
    subscription = next(item for item in authenticated_client.get("/api/v1/billing/subscriptions").json() if item["id"] == failed["subscription_id"])
    assert subscription["status"] == "cancelled"
    assert subscription["cancellation_reason"] == "Payment recovery exhausted"


def test_signed_webhook_rejects_tampering_and_is_idempotent(authenticated_client):
    seed_billing(authenticated_client)
    invoice = next(item for item in authenticated_client.get("/api/v1/billing/invoices").json() if item["status"] == "failed")
    payload = GatewayWebhookPayload(
        event_id=f"evt_{uuid4().hex}",
        event_type="payment.paid",
        owner_user_id=1,
        invoice_id=invoice["id"],
        amount=invoice["total"],
        currency="INR",
        gateway_reference=f"ref_{uuid4().hex}",
        attempt_number=0,
        idempotency_key=f"webhook-{uuid4().hex}",
    ).model_dump(mode="json")
    rejected = authenticated_client.post("/api/v1/billing/webhooks/mock-gateway", json=payload, headers={"X-BillFlow-Signature": "tampered"})
    assert rejected.status_code == 400
    signature = sign_webhook(payload, get_settings().billing_webhook_secret)
    accepted = authenticated_client.post("/api/v1/billing/webhooks/mock-gateway", json=payload, headers={"X-BillFlow-Signature": signature})
    assert accepted.status_code == 200, accepted.text
    repeated = authenticated_client.post("/api/v1/billing/webhooks/mock-gateway", json=payload, headers={"X-BillFlow-Signature": signature})
    assert repeated.status_code == 200
    assert repeated.json()["duplicate"] is True


def test_immediate_cancellation_records_unused_period_refund(authenticated_client):
    seed_billing(authenticated_client)
    subscription = next(item for item in authenticated_client.get("/api/v1/billing/subscriptions").json() if item["customer_name"] == "Acme Analytics")
    response = authenticated_client.post(
        f"/api/v1/billing/subscriptions/{subscription['id']}/cancel",
        json={"timing": "immediate", "refund_unused": True, "reason": "Customer closed account"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["subscription"]["status"] == "cancelled"
    assert response.json()["refund_id"] is not None
    invoices = authenticated_client.get("/api/v1/billing/invoices").json()
    assert any(item["status"] in {"partially_refunded", "refunded"} for item in invoices)
    assert any(any(line["line_type"] == "refund" for line in item["line_items"]) for item in invoices)


def test_dashboard_tax_notifications_and_customer_audit(authenticated_client):
    seed_billing(authenticated_client)
    dashboard = authenticated_client.get("/api/v1/billing/dashboard")
    assert dashboard.status_code == 200
    metrics = dashboard.json()["metrics"]
    assert metrics["active_subscriptions"] >= 1
    assert metrics["mrr"] > 0
    assert dashboard.json()["revenue_by_plan"]
    assert dashboard.json()["invoice_status"]
    summary = authenticated_client.get("/api/v1/billing/tax-summary")
    assert summary.status_code == 200
    assert summary.json()["total_tax"] > 0
    notifications = authenticated_client.get("/api/v1/billing/notifications").json()
    assert {item["event_type"] for item in notifications} >= {"payment_received", "payment_failed"}
    customer = authenticated_client.get("/api/v1/billing/customers").json()[0]
    audit = authenticated_client.get(f"/api/v1/billing/audit?customer_id={customer['id']}")
    assert audit.status_code == 200
    assert all(str(item["detail"].get("customer_id")) == str(customer["id"]) for item in audit.json())


def test_billing_workspace_is_tenant_isolated(client):
    first = client.post(
        "/api/v1/auth/register",
        json={"email": "first@example.com", "full_name": "First Owner", "password": "SecurePass123", "monthly_income": 1, "minimum_balance": 0},
    )
    assert first.status_code == 201
    seed_billing(client)
    assert len(client.get("/api/v1/billing/plans").json()) == 3
    client.post("/api/v1/auth/logout")
    second = client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.com", "full_name": "Second Owner", "password": "SecurePass123", "monthly_income": 1, "minimum_balance": 0},
    )
    assert second.status_code == 201
    assert client.get("/api/v1/billing/plans").json() == []
    assert client.get("/api/v1/billing/customers").json() == []
    assert client.get("/api/v1/billing/invoices").json() == []
