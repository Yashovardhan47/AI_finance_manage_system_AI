from __future__ import annotations

from uuid import uuid4

from locust import HttpUser, between, task


class BillingOperator(HttpUser):
    """Authenticated, read-heavy operator traffic with isolated demo tenants."""

    wait_time = between(0.2, 0.8)

    def on_start(self) -> None:
        identity = uuid4().hex
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": f"load-{identity}@example.com",
                "full_name": "Load Test Operator",
                "password": "LoadTestPass123",
                "monthly_income": 100000,
                "minimum_balance": 20000,
            },
            name="POST /auth/register",
        )
        if response.status_code != 201:
            response.raise_for_status()
        seed = self.client.post("/api/v1/billing/demo/seed", name="POST /billing/demo/seed")
        if seed.status_code != 200:
            seed.raise_for_status()

    @task(5)
    def dashboard(self) -> None:
        self.client.get("/api/v1/billing/dashboard", name="GET /billing/dashboard")

    @task(4)
    def invoices(self) -> None:
        self.client.get("/api/v1/billing/invoices", name="GET /billing/invoices")

    @task(3)
    def subscriptions(self) -> None:
        self.client.get("/api/v1/billing/subscriptions", name="GET /billing/subscriptions")

    @task(2)
    def recovery_queue(self) -> None:
        self.client.get("/api/v1/billing/retries", name="GET /billing/retries")

    @task
    def tax_and_audit(self) -> None:
        self.client.get("/api/v1/billing/tax-summary", name="GET /billing/tax-summary")
        self.client.get("/api/v1/billing/audit?limit=30", name="GET /billing/audit")
