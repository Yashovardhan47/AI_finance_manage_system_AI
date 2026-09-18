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
    assert confirmed.json()["provider_sync_status"] in {"confirmed", "not_required"}
    receipt = authenticated_client.get(f"/api/v1/payments/{prepared.json()['id']}/receipt")
    assert receipt.status_code == 200
    assert receipt.headers["content-type"] == "application/pdf"
    assert receipt.content.startswith(b"%PDF")
    paid_bill = next(item for item in authenticated_client.get("/api/v1/bills").json() if item["id"] == bill["id"])
    assert paid_bill["status"] == "paid"
    if paid_bill["provider_connection_id"]:
        assert paid_bill["sync_status"] == "synced"
        assert paid_bill["external_status"] in {"active", "cleared"}


def test_payment_idempotency(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    bill = authenticated_client.get("/api/v1/bills").json()[0]
    account = authenticated_client.get("/api/v1/accounts").json()[0]
    payload = {"bill_id": bill["id"], "account_id": account["id"], "idempotency_key": "repeat-safe-key"}
    first = authenticated_client.post("/api/v1/payments/prepare", json=payload)
    second = authenticated_client.post("/api/v1/payments/prepare", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_subscription_payment_activates_original_provider_account(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    bills = authenticated_client.get("/api/v1/bills").json()
    subscription = next(item for item in bills if item["service_action"] == "activate_subscription")
    account = authenticated_client.get("/api/v1/accounts").json()[0]
    prepared = authenticated_client.post(
        "/api/v1/payments/prepare",
        json={"bill_id": subscription["id"], "account_id": account["id"], "idempotency_key": "activate-streamplus"},
    ).json()
    confirmed = authenticated_client.post(f"/api/v1/payments/{prepared['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["provider_sync_status"] == "confirmed"
    assert confirmed.json()["provider_confirmation_id"]
    state = authenticated_client.get(
        f"/api/v1/integrations/connections/{subscription['provider_connection_id']}/provider-state"
    ).json()
    assert state["state"]["subscription_status"] == "active"
    assert state["state"]["plan"] == "StreamPlus Premium"


def test_home_bill_payment_clears_provider_due(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    bills = authenticated_client.get("/api/v1/bills").json()
    home_bill = next(item for item in bills if item["biller"] == "GridHome Energy")
    account = authenticated_client.get("/api/v1/accounts").json()[0]
    prepared = authenticated_client.post(
        "/api/v1/payments/prepare",
        json={"bill_id": home_bill["id"], "account_id": account["id"], "idempotency_key": "clear-home-due"},
    ).json()
    confirmed = authenticated_client.post(f"/api/v1/payments/{prepared['id']}/confirm")
    assert confirmed.status_code == 200
    state = authenticated_client.get(
        f"/api/v1/integrations/connections/{home_bill['provider_connection_id']}/provider-state"
    ).json()
    assert state["state"]["due_status"] == "cleared"
    events = authenticated_client.get("/api/v1/integrations/events").json()
    assert any(event["event_type"] == "provider.utility_due_cleared" for event in events)


def test_browse_apps_returns_every_plan_with_full_details_and_ai_decisions(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    overview = authenticated_client.get("/api/v1/marketplace/apps")
    assert overview.status_code == 200
    assert len(overview.json()["items"]) == 5
    assert {item["slug"] for item in overview.json()["items"]} == {
        "streamplus", "musicwave", "cloudbox", "fitpulse", "learnpro"
    }

    detail = authenticated_client.get("/api/v1/marketplace/apps/streamplus")
    assert detail.status_code == 200
    assert [plan["id"] for plan in detail.json()["plans"]] == ["mobile", "standard", "premium"]
    premium = next(plan for plan in detail.json()["plans"] if plan["id"] == "premium")
    assert premium["price"] == 799.0
    assert premium["trial_days"] == 7
    assert premium["limits"]["simultaneous_streams"] == 4
    assert premium["cancellation"]
    assert premium["refund_policy"]
    assert premium["recommendation"]["decision"] in {"subscribe", "wait", "not_recommended"}
    assert premium["recommendation"]["conflicting_deadlines"]
    assert "affordability" in premium["recommendation"]["explanation"].lower()


def test_marketplace_interactions_change_preference_signal_but_not_safety_data(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    before = authenticated_client.get("/api/v1/marketplace/apps/cloudbox").json()
    before_plan = next(plan for plan in before["plans"] if plan["id"] == "storage-100")
    response = authenticated_client.post(
        "/api/v1/marketplace/interactions",
        json={"app_slug": "cloudbox", "plan_id": "storage-100", "action": "shortlisted", "context": {"surface": "test"}},
    )
    assert response.status_code == 201
    after = authenticated_client.get("/api/v1/marketplace/apps/cloudbox").json()
    after_plan = next(plan for plan in after["plans"] if plan["id"] == "storage-100")
    assert after_plan["recommendation"]["preference_signal"] > before_plan["recommendation"]["preference_signal"]
    assert after_plan["recommendation"]["projected_lowest_balance"] == before_plan["recommendation"]["projected_lowest_balance"]
    history = authenticated_client.get("/api/v1/marketplace/interactions").json()
    assert history[0]["action"] == "shortlisted"


def test_unsafe_subscription_needs_warning_acknowledgement(authenticated_client):
    detail = authenticated_client.get("/api/v1/marketplace/apps/learnpro").json()
    annual = next(plan for plan in detail["plans"] if plan["id"] == "annual")
    assert annual["recommendation"]["decision"] == "not_recommended"
    blocked = authenticated_client.post(
        "/api/v1/marketplace/subscribe-intent",
        json={"app_slug": "learnpro", "plan_id": "annual"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "recommendation_acknowledgement_required"
    overridden = authenticated_client.post(
        "/api/v1/marketplace/subscribe-intent",
        json={"app_slug": "learnpro", "plan_id": "annual", "override_warning_acknowledged": True},
    )
    assert overridden.status_code == 201
    assert overridden.json()["status"] == "payment_required"
    assert overridden.json()["bill"]["status"] == "due"
    assert overridden.json()["connection"]["provider_state"]["subscription_status"] == "inactive"


def test_browse_to_payment_activates_the_exact_selected_plan(authenticated_client):
    authenticated_client.post("/api/v1/demo/seed")
    intent = authenticated_client.post(
        "/api/v1/marketplace/subscribe-intent",
        json={"app_slug": "musicwave", "plan_id": "individual"},
    )
    assert intent.status_code == 201
    payload = intent.json()
    assert payload["recommendation"]["decision"] == "subscribe"
    assert payload["connection"]["provider_state"]["subscription_status"] == "inactive"
    assert payload["connection"]["provider_state"]["pending_plan"]["id"] == "individual"

    account = authenticated_client.get("/api/v1/accounts").json()[0]
    prepared = authenticated_client.post(
        "/api/v1/payments/prepare",
        json={"bill_id": payload["bill"]["id"], "account_id": account["id"], "idempotency_key": "activate-musicwave-individual"},
    ).json()
    assert prepared["status"] == "requires_authorization"
    confirmed = authenticated_client.post(f"/api/v1/payments/{prepared['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["provider_sync_status"] == "confirmed"

    state = authenticated_client.get(
        f"/api/v1/integrations/connections/{payload['connection']['id']}/provider-state"
    ).json()["state"]
    assert state["subscription_status"] == "active"
    assert state["plan"] == "Individual"
    assert state["plan_id"] == "individual"
    interactions = authenticated_client.get("/api/v1/marketplace/interactions").json()
    assert any(item["action"] == "subscribed" and item["plan_id"] == "individual" for item in interactions)
