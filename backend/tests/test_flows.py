def test_register_and_profile(authenticated_client):
    response = authenticated_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "demo@example.com"


def test_demo_seed_generates_explainable_intelligence(authenticated_client):
    seed = authenticated_client.post("/api/v1/demo/seed")
    assert seed.status_code == 200
    plan = authenticated_client.get("/api/v1/ai/safe-pay-plan")
    health = authenticated_client.get("/api/v1/ai/health")
    anomalies = authenticated_client.get("/api/v1/ai/anomalies")
    assert plan.status_code == health.status_code == anomalies.status_code == 200
    assert len(plan.json()["items"]) == 5
    assert plan.json()["policy"]["never_pay_without_confirmation"] is True
    assert 0 <= health.json()["score"] <= 100
    assert anomalies.json()["count"] >= 1
    assert "explanation" in anomalies.json()["items"][0]


def test_payment_requires_prepare_then_confirmation(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    bill = authenticated_client.get("/api/v1/bills").json()[0]
    account = authenticated_client.get("/api/v1/accounts").json()[0]
    prepared = authenticated_client.post(
        "/api/v1/payments/prepare",
        json={"bill_id": bill["id"], "account_id": account["id"], "idempotency_key": "test-payment-0001"},
    )
    assert prepared.status_code == 200
    assert prepared.json()["status"] == "requires_authorization"
    confirmed = authenticated_client.post(f"/api/v1/payments/{prepared.json()['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "succeeded"
    receipt = authenticated_client.get(f"/api/v1/payments/{prepared.json()['id']}/receipt")
    assert receipt.status_code == 200
    assert receipt.headers["content-type"] == "application/pdf"
    assert receipt.content.startswith(b"%PDF")
    paid_bill = next(item for item in authenticated_client.get("/api/v1/bills").json() if item["id"] == bill["id"])
    assert paid_bill["status"] == "paid"


def test_payment_idempotency(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    bill = authenticated_client.get("/api/v1/bills").json()[0]
    account = authenticated_client.get("/api/v1/accounts").json()[0]
    payload = {"bill_id": bill["id"], "account_id": account["id"], "idempotency_key": "repeat-safe-key"}
    first = authenticated_client.post("/api/v1/payments/prepare", json=payload)
    second = authenticated_client.post("/api/v1/payments/prepare", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
