from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models import ProviderConnection, User
from app.operations_models import (
    ActionRequest,
    ConsentRecord,
    ExceptionCase,
    FinancialPolicy,
    Obligation,
    ObligationDocument,
    OutcomeEvent,
    Recommendation,
    Scenario,
)
from app.operations_schemas import (
    ConsentCreate,
    ExceptionResolve,
    FinancialPolicyRead,
    FinancialPolicyUpdate,
    ObligationCreate,
    ObligationDocumentCreate,
    ObligationDocumentRead,
    ObligationRead,
    OutcomeCreate,
    RecommendationDecision,
    RecommendationRead,
    ScenarioCreate,
)
from app.services.audit import write_audit
from app.services.financial_operations import (
    approve_recommendation,
    command_center,
    get_or_create_policy,
    new_consent_reference,
    record_outcome,
    refresh_recommendations,
    simulate_scenario,
    sync_obligations_from_bills,
)


router = APIRouter(prefix="/operations", tags=["financial operations"])


def action_payload(item: ActionRequest) -> dict:
    return {
        "id": item.id,
        "recommendation_id": item.recommendation_id,
        "obligation_id": item.obligation_id,
        "action_type": item.action_type,
        "idempotency_key": item.idempotency_key,
        "status": item.status,
        "payload": item.payload,
        "policy_evaluation": item.policy_evaluation,
        "approved_at": item.approved_at,
        "executed_at": item.executed_at,
        "failure_reason": item.failure_reason,
        "created_at": item.created_at,
    }


def exception_payload(item: ExceptionCase) -> dict:
    return {
        "id": item.id,
        "obligation_id": item.obligation_id,
        "outcome_event_id": item.outcome_event_id,
        "case_type": item.case_type,
        "severity": item.severity,
        "status": item.status,
        "summary": item.summary,
        "evidence": item.evidence,
        "resolution": item.resolution,
        "created_at": item.created_at,
        "resolved_at": item.resolved_at,
    }


def outcome_payload(item: OutcomeEvent) -> dict:
    return {
        "id": item.id,
        "obligation_id": item.obligation_id,
        "action_request_id": item.action_request_id,
        "event_type": item.event_type,
        "source": item.source,
        "status": item.status,
        "provider_reference": item.provider_reference,
        "evidence": item.evidence,
        "occurred_at": item.occurred_at,
    }


def scenario_payload(item: Scenario) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "assumptions": item.assumptions,
        "result": item.result,
        "created_at": item.created_at,
    }


def consent_payload(item: ConsentRecord) -> dict:
    return {
        "id": item.id,
        "provider_connection_id": item.provider_connection_id,
        "purpose": item.purpose,
        "data_categories": item.data_categories,
        "status": item.status,
        "consent_reference": item.consent_reference,
        "granted_at": item.granted_at,
        "expires_at": item.expires_at,
        "revoked_at": item.revoked_at,
    }


def serialize_center(payload: dict) -> dict:
    return {
        **payload,
        "policy": FinancialPolicyRead.model_validate(payload["policy"]).model_dump(mode="json"),
        "obligations": [
            ObligationRead.model_validate(item).model_dump(mode="json") for item in payload["obligations"]
        ],
        "recommendations": [
            RecommendationRead.model_validate(item).model_dump(mode="json")
            for item in payload["recommendations"]
        ],
        "exceptions": [exception_payload(item) for item in payload["exceptions"]],
        "actions": [action_payload(item) for item in payload["actions"]],
    }


@router.get("/command-center")
def get_command_center(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    payload = serialize_center(command_center(db, user))
    db.commit()
    return payload


@router.post("/bootstrap")
def bootstrap(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    recommendations = refresh_recommendations(db, user)
    write_audit(
        db,
        user_id=user.id,
        action="operations.bootstrap_completed",
        entity_type="financial_operations",
        detail={"recommendations_generated": len(recommendations)},
    )
    db.commit()
    return serialize_center(command_center(db, user))


@router.get("/obligations", response_model=list[ObligationRead])
def list_obligations(
    obligation_status: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Obligation]:
    sync_obligations_from_bills(db, user)
    query = select(Obligation).where(Obligation.user_id == user.id)
    if obligation_status:
        query = query.where(Obligation.status == obligation_status)
    if category:
        query = query.where(Obligation.category == category)
    items = list(db.scalars(query.order_by(Obligation.due_date, Obligation.id)))
    db.commit()
    return items


@router.post("/obligations", response_model=ObligationRead, status_code=status.HTTP_201_CREATED)
def create_obligation(
    payload: ObligationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Obligation:
    obligation = Obligation(user_id=user.id, **payload.model_dump())
    db.add(obligation)
    db.flush()
    write_audit(
        db,
        user_id=user.id,
        action="obligation.created",
        entity_type="obligation",
        entity_id=obligation.id,
        detail={"amount": str(obligation.amount), "due_date": obligation.due_date.isoformat()},
    )
    db.commit()
    db.refresh(obligation)
    return obligation


@router.post(
    "/obligations/{obligation_id}/documents",
    response_model=ObligationDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_obligation_document(
    obligation_id: int,
    payload: ObligationDocumentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ObligationDocument:
    obligation = db.scalar(
        select(Obligation).where(Obligation.id == obligation_id, Obligation.user_id == user.id)
    )
    if not obligation:
        raise HTTPException(status_code=404, detail="Obligation not found")
    document = ObligationDocument(user_id=user.id, obligation_id=obligation.id, **payload.model_dump())
    db.add(document)
    db.flush()
    write_audit(
        db,
        user_id=user.id,
        action="obligation.document_added",
        entity_type="obligation_document",
        entity_id=document.id,
        detail={"obligation_id": obligation.id, "extraction_status": document.extraction_status},
    )
    db.commit()
    db.refresh(document)
    return document


@router.get("/obligations/{obligation_id}/documents", response_model=list[ObligationDocumentRead])
def list_obligation_documents(
    obligation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ObligationDocument]:
    if not db.scalar(
        select(Obligation.id).where(Obligation.id == obligation_id, Obligation.user_id == user.id)
    ):
        raise HTTPException(status_code=404, detail="Obligation not found")
    return list(
        db.scalars(
            select(ObligationDocument)
            .where(
                ObligationDocument.obligation_id == obligation_id,
                ObligationDocument.user_id == user.id,
            )
            .order_by(ObligationDocument.created_at.desc())
        )
    )


@router.get("/policy", response_model=FinancialPolicyRead)
def get_policy(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialPolicy:
    policy = get_or_create_policy(db, user)
    db.commit()
    db.refresh(policy)
    return policy


@router.put("/policy", response_model=FinancialPolicyRead)
def update_policy(
    payload: FinancialPolicyUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialPolicy:
    policy = get_or_create_policy(db, user)
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(policy, key, value)
    write_audit(
        db,
        user_id=user.id,
        action="financial_policy.updated",
        entity_type="financial_policy",
        entity_id=policy.id,
        detail={
            **{key: str(value) for key, value in changes.items() if not isinstance(value, list)},
            **{key: value for key, value in changes.items() if isinstance(value, list)},
        },
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.post("/recommendations/refresh", response_model=list[RecommendationRead])
def regenerate_recommendations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Recommendation]:
    items = refresh_recommendations(db, user)
    write_audit(
        db,
        user_id=user.id,
        action="recommendations.refreshed",
        entity_type="recommendation",
        detail={"count": len(items), "engine": "financial-ops-rules-v1"},
    )
    db.commit()
    return items


@router.post("/recommendations/{recommendation_id}/decision")
def decide_recommendation(
    recommendation_id: int,
    payload: RecommendationDecision,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    recommendation = db.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == user.id,
        )
    )
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    if payload.decision == "reject":
        if recommendation.status == "approved":
            raise HTTPException(status_code=409, detail="An approved recommendation cannot be rejected")
        recommendation.status = "rejected"
        recommendation.decided_at = datetime.now(timezone.utc)
        write_audit(
            db,
            user_id=user.id,
            action="recommendation.rejected",
            entity_type="recommendation",
            entity_id=recommendation.id,
            detail={"note": payload.note},
        )
        db.commit()
        return {
            "recommendation": RecommendationRead.model_validate(recommendation).model_dump(mode="json"),
            "action_request": None,
        }

    existing = db.scalar(
        select(ActionRequest).where(
            ActionRequest.user_id == user.id,
            ActionRequest.recommendation_id == recommendation.id,
        )
    )
    if existing:
        return {
            "recommendation": RecommendationRead.model_validate(recommendation).model_dump(mode="json"),
            "action_request": action_payload(existing),
        }
    if recommendation.status != "pending":
        raise HTTPException(status_code=409, detail=f"Recommendation is already {recommendation.status}")
    try:
        action = approve_recommendation(
            db,
            user,
            recommendation,
            idempotency_key=payload.idempotency_key,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    write_audit(
        db,
        user_id=user.id,
        action="recommendation.approved",
        entity_type="action_request",
        entity_id=action.id,
        detail={
            "recommendation_id": recommendation.id,
            "action_status": action.status,
            "external_authorization_required": True,
        },
    )
    db.commit()
    return {
        "recommendation": RecommendationRead.model_validate(recommendation).model_dump(mode="json"),
        "action_request": action_payload(action),
    }


@router.get("/actions")
def list_actions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = list(
        db.scalars(
            select(ActionRequest)
            .where(ActionRequest.user_id == user.id)
            .order_by(ActionRequest.created_at.desc())
        )
    )
    return [action_payload(item) for item in items]


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
def create_scenario(
    payload: ScenarioCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    scenario = simulate_scenario(db, user, **payload.model_dump())
    write_audit(
        db,
        user_id=user.id,
        action="scenario.simulated",
        entity_type="scenario",
        entity_id=scenario.id,
        detail={"decision": scenario.result["decision"], "reserve_breach": scenario.result["reserve_breach"]},
    )
    db.commit()
    return scenario_payload(scenario)


@router.get("/scenarios")
def list_scenarios(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = list(
        db.scalars(
            select(Scenario)
            .where(Scenario.user_id == user.id)
            .order_by(Scenario.created_at.desc())
            .limit(limit)
        )
    )
    return [scenario_payload(item) for item in items]


@router.post("/outcomes", status_code=status.HTTP_201_CREATED)
def create_outcome(
    payload: OutcomeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    obligation = db.scalar(
        select(Obligation).where(
            Obligation.id == payload.obligation_id,
            Obligation.user_id == user.id,
        )
    )
    if not obligation:
        raise HTTPException(status_code=404, detail="Obligation not found")
    if payload.action_request_id and not db.scalar(
        select(ActionRequest.id).where(
            ActionRequest.id == payload.action_request_id,
            ActionRequest.user_id == user.id,
            ActionRequest.obligation_id == obligation.id,
        )
    ):
        raise HTTPException(status_code=404, detail="Action request not found for this obligation")
    event, case = record_outcome(
        db,
        user,
        obligation,
        action_request_id=payload.action_request_id,
        event_type=payload.event_type,
        source=payload.source,
        status=payload.status,
        provider_reference=payload.provider_reference,
        expected_status=payload.expected_status,
        actual_status=payload.actual_status,
        evidence=payload.evidence,
    )
    write_audit(
        db,
        user_id=user.id,
        action="outcome.recorded",
        entity_type="outcome_event",
        entity_id=event.id,
        detail={"status": event.status, "exception_opened": bool(case)},
    )
    db.commit()
    return {
        "event": outcome_payload(event),
        "exception": exception_payload(case) if case else None,
    }


@router.get("/outcomes")
def list_outcomes(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = list(
        db.scalars(
            select(OutcomeEvent)
            .where(OutcomeEvent.user_id == user.id)
            .order_by(OutcomeEvent.occurred_at.desc())
        )
    )
    return [outcome_payload(item) for item in items]


@router.get("/exceptions")
def list_exceptions(
    case_status: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(ExceptionCase).where(ExceptionCase.user_id == user.id)
    if case_status:
        query = query.where(ExceptionCase.status == case_status)
    items = list(db.scalars(query.order_by(ExceptionCase.created_at.desc())))
    return [exception_payload(item) for item in items]


@router.post("/exceptions/{case_id}/resolve")
def resolve_exception(
    case_id: int,
    payload: ExceptionResolve,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    case = db.scalar(
        select(ExceptionCase).where(ExceptionCase.id == case_id, ExceptionCase.user_id == user.id)
    )
    if not case:
        raise HTTPException(status_code=404, detail="Exception case not found")
    case.status = "resolved"
    case.resolution = payload.resolution
    case.resolved_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.id,
        action="exception.resolved",
        entity_type="exception_case",
        entity_id=case.id,
        detail={"resolution": payload.resolution},
    )
    db.commit()
    return exception_payload(case)


@router.post("/consents", status_code=status.HTTP_201_CREATED)
def create_consent(
    payload: ConsentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if payload.provider_connection_id and not db.scalar(
        select(ProviderConnection.id).where(
            ProviderConnection.id == payload.provider_connection_id,
            ProviderConnection.user_id == user.id,
        )
    ):
        raise HTTPException(status_code=404, detail="Provider connection not found")
    consent = ConsentRecord(
        user_id=user.id,
        consent_reference=new_consent_reference(),
        **payload.model_dump(),
    )
    db.add(consent)
    db.flush()
    write_audit(
        db,
        user_id=user.id,
        action="consent.granted",
        entity_type="consent",
        entity_id=consent.id,
        detail={"purpose": consent.purpose, "data_categories": consent.data_categories},
    )
    db.commit()
    return consent_payload(consent)


@router.get("/consents")
def list_consents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = list(
        db.scalars(
            select(ConsentRecord)
            .where(ConsentRecord.user_id == user.id)
            .order_by(ConsentRecord.granted_at.desc())
        )
    )
    return [consent_payload(item) for item in items]


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(
    consent_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    consent = db.scalar(
        select(ConsentRecord).where(ConsentRecord.id == consent_id, ConsentRecord.user_id == user.id)
    )
    if not consent:
        raise HTTPException(status_code=404, detail="Consent not found")
    consent.status = "revoked"
    consent.revoked_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.id,
        action="consent.revoked",
        entity_type="consent",
        entity_id=consent.id,
    )
    db.commit()
    return consent_payload(consent)
