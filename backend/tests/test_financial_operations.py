from datetime import date, timedelta


def bootstrap_operations(authenticated_client):
    assert authenticated_client.post("/api/v1/demo/seed").status_code == 200
    response = authenticated_client.post("/api/v1/operations/bootstrap")
    assert response.status_code == 200, response.text
    return response.json()


def test_obligation_graph_and_financial_twin_are_bootstrapped_idempotently(authenticated_client):
    first = bootstrap_operations(authenticated_client)
    assert first["summary"]["active_obligations"] >= 4
    assert first["summary"]["pending_decisions"] == len(first["recommendations"])
    assert len(first["forecast"]["points"]) == 91
    assert first["forecast"]["confidence"] >= 0.45
    assert first["categories"]
    assert all(item["source"] == "bill" for item in first["obligations"])

    second = authenticated_client.post("/api/v1/operations/bootstrap")
    assert second.status_code == 200
    second_payload = second.json()
    assert len(second_payload["obligations"]) == len(first["obligations"])
    external_refs = [item["external_reference"] for item in second_payload["obligations"]]
    assert len(external_refs) == len(set(external_refs))


def test_policy_control_and_approval_request_are_idempotent(authenticated_client):
    bootstrap_operations(authenticated_client)
    policy = authenticated_client.put(
        "/api/v1/operations/policy",
        json={
            "autonomy_mode": "prepare",
            "minimum_reserve": 9000,
            "max_preparable_amount": 100000,
            "require_provider_confirmation": True,
        },
    )
    assert policy.status_code == 200
    assert policy.json()["autonomy_mode"] == "prepare"

    refreshed = authenticated_client.post("/api/v1/operations/recommendations/refresh")
    assert refreshed.status_code == 200
    recommendation = refreshed.json()[0]
    payload = {
        "decision": "approve",
        "idempotency_key": "financial-ops-approval-0001",
        "note": "User reviewed forecast and approved preparation",
    }
    first = authenticated_client.post(
        f"/api/v1/operations/recommendations/{recommendation['id']}/decision",
        json=payload,
    )
    second = authenticated_client.post(
        f"/api/v1/operations/recommendations/{recommendation['id']}/decision",
        json=payload,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["action_request"]["id"] == second.json()["action_request"]["id"]
    assert first.json()["action_request"]["status"] == "ready_for_handoff"
    evaluation = first.json()["action_request"]["policy_evaluation"]
    assert evaluation["requires_explicit_user_approval"] is True
    assert evaluation["requires_external_authorization"] is True


def test_advise_mode_never_claims_execution(authenticated_client):
    center = bootstrap_operations(authenticated_client)
    recommendation = center["recommendations"][0]
    response = authenticated_client.post(
        f"/api/v1/operations/recommendations/{recommendation['id']}/decision",
        json={
            "decision": "approve",
            "idempotency_key": "advice-only-approval",
        },
    )
    assert response.status_code == 200
    action = response.json()["action_request"]
    assert action["status"] == "approved_advice"
    assert action["executed_at"] is None
    assert action["policy_evaluation"]["can_prepare"] is False


def test_what_if_scenario_recalculates_reserve_impact(authenticated_client):
    bootstrap_operations(authenticated_client)
    response = authenticated_client.post(
        "/api/v1/operations/scenarios",
        json={
            "name": "Premium annual subscription",
            "amount": 250000,
            "due_date": (date.today() + timedelta(days=5)).isoformat(),
            "category": "subscription",
            "essential": False,
            "recurring_monthly": False,
        },
    )
    assert response.status_code == 201
    result = response.json()["result"]
    assert result["reserve_breach"] is True
    assert result["decision"] == "wait_or_reduce"
    assert len(result["points"]) == 91
    assert result["projected_lowest_balance"] < result["baseline_lowest_balance"]


def test_provider_outcome_mismatch_opens_exception_case(authenticated_client):
    center = bootstrap_operations(authenticated_client)
    obligation = center["obligations"][0]
    response = authenticated_client.post(
        "/api/v1/operations/outcomes",
        json={
            "obligation_id": obligation["id"],
            "event_type": "provider_status_checked",
            "source": "reconciliation",
            "status": "mismatch",
            "provider_reference": "provider-check-001",
            "expected_status": "cleared",
            "actual_status": "due",
            "evidence": {"attempt": 1},
        },
    )
    assert response.status_code == 201
    assert response.json()["exception"]["case_type"] == "provider_outcome_mismatch"

    cases = authenticated_client.get("/api/v1/operations/exceptions?status=open")
    assert cases.status_code == 200
    assert len(cases.json()) == 1
    assert cases.json()[0]["severity"] == "medium"

    resolved = authenticated_client.post(
        f"/api/v1/operations/exceptions/{cases.json()[0]['id']}/resolve",
        json={"resolution": "Provider confirmed the account after manual review."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_contract_metadata_and_consent_lifecycle(authenticated_client):
    center = bootstrap_operations(authenticated_client)
    obligation = center["obligations"][0]
    document = authenticated_client.post(
        f"/api/v1/operations/obligations/{obligation['id']}/documents",
        json={
            "filename": "renewal-notice.pdf",
            "media_type": "application/pdf",
            "content_hash": "0123456789abcdef0123456789abcdef",
            "extraction_status": "review_required",
            "extraction_confidence": 0.82,
            "extracted_fields": {
                "renewal_date": obligation["due_date"],
                "price_change_percent": 12,
                "cancellation_window_days": 7,
            },
        },
    )
    assert document.status_code == 201
    assert document.json()["extracted_fields"]["price_change_percent"] == 12

    consent = authenticated_client.post(
        "/api/v1/operations/consents",
        json={
            "purpose": "Generate a 90-day cash-flow forecast",
            "data_categories": ["balances", "transactions", "upcoming_bills"],
        },
    )
    assert consent.status_code == 201
    assert consent.json()["status"] == "active"
    revoked = authenticated_client.post(
        f"/api/v1/operations/consents/{consent.json()['id']}/revoke"
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_financial_operations_are_tenant_scoped(authenticated_client):
    bootstrap_operations(authenticated_client)
    assert authenticated_client.post("/api/v1/auth/logout").status_code == 204
    registered = authenticated_client.post(
        "/api/v1/auth/register",
        json={
            "email": "second@example.com",
            "full_name": "Second User",
            "password": "SecurePass456",
            "monthly_income": 50000,
            "minimum_balance": 8000,
        },
    )
    assert registered.status_code == 201
    center = authenticated_client.get("/api/v1/operations/command-center")
    assert center.status_code == 200
    payload = center.json()
    assert payload["summary"]["active_obligations"] == 0
    assert payload["obligations"] == []
    assert payload["recommendations"] == []
