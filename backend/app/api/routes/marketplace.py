from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models import Bill, FinancialAccount, MarketplaceInteraction, ProviderConnection, Transaction, User
from app.schemas import (
    BillRead,
    MarketplaceInteractionCreate,
    MarketplaceInteractionRead,
    ProviderConnectionRead,
    SubscriptionIntentCreate,
)
from app.services.audit import write_audit
from app.services.marketplace import (
    app_for,
    marketplace_app_detail,
    marketplace_overview,
    plan_for,
    recommend_plan,
)
from app.services.provider_connectors import SandboxProviderConnector, definition_for


router = APIRouter(prefix="/marketplace", tags=["subscription marketplace"])


def _context(db: Session, user_id: int) -> tuple[
    list[FinancialAccount],
    list[Bill],
    list[Transaction],
    list[MarketplaceInteraction],
    list[ProviderConnection],
]:
    accounts = list(db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user_id)))
    bills = list(db.scalars(select(Bill).where(Bill.user_id == user_id)))
    transactions = list(db.scalars(select(Transaction).where(Transaction.user_id == user_id)))
    interactions = list(
        db.scalars(
            select(MarketplaceInteraction)
            .where(MarketplaceInteraction.user_id == user_id)
            .order_by(MarketplaceInteraction.created_at.desc())
        )
    )
    connections = list(db.scalars(select(ProviderConnection).where(ProviderConnection.user_id == user_id)))
    return accounts, bills, transactions, interactions, connections


@router.get("/apps")
def browse_apps(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return marketplace_overview(user, *_context(db, user.id))


@router.get("/apps/{app_slug}")
def browse_app_details(
    app_slug: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return marketplace_app_detail(user, app_slug, *_context(db, user.id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/recommendations")
def subscription_recommendations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    overview = marketplace_overview(user, *_context(db, user.id))
    ranking = sorted(
        (
            {
                "app_slug": item["slug"],
                "app_name": item["name"],
                "category": item["category"],
                **item["best_match"],
            }
            for item in overview["items"]
        ),
        key=lambda item: ({"subscribe": 2, "wait": 1, "not_recommended": 0}[item["decision"]], item["score"]),
        reverse=True,
    )
    return {"items": ranking, "method": overview["method"], "safety_rule": overview["safety_rule"]}


@router.get("/interactions", response_model=list[MarketplaceInteractionRead])
def interaction_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MarketplaceInteraction]:
    return list(
        db.scalars(
            select(MarketplaceInteraction)
            .where(MarketplaceInteraction.user_id == user.id)
            .order_by(MarketplaceInteraction.created_at.desc())
            .limit(100)
        )
    )


@router.post("/interactions", response_model=MarketplaceInteractionRead, status_code=status.HTTP_201_CREATED)
def record_interaction(
    payload: MarketplaceInteractionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketplaceInteraction:
    try:
        app = app_for(payload.app_slug)
        if payload.plan_id:
            plan_for(payload.app_slug, payload.plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    interaction = MarketplaceInteraction(user_id=user.id, **payload.model_dump())
    db.add(interaction)
    db.flush()
    write_audit(
        db,
        user_id=user.id,
        action=f"marketplace.{payload.action}",
        entity_type="subscription_plan" if payload.plan_id else "marketplace_app",
        entity_id=f"{app['slug']}:{payload.plan_id}" if payload.plan_id else app["slug"],
        detail={"app": app["name"], "plan_id": payload.plan_id},
    )
    db.commit()
    db.refresh(interaction)
    return interaction


@router.post("/subscribe-intent", status_code=status.HTTP_201_CREATED)
def create_subscription_intent(
    payload: SubscriptionIntentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        app, plan = plan_for(payload.app_slug, payload.plan_id)
        definition = definition_for(payload.app_slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    accounts, bills, transactions, interactions, connections = _context(db, user.id)
    recommendation = recommend_plan(
        user, app, plan, accounts, bills, transactions, interactions, connections
    )
    connection = next((item for item in connections if item.provider_slug == payload.app_slug), None)
    provider_state = connection.provider_state if connection else {}
    same_plan_active = provider_state.get("subscription_status") == "active" and (
        provider_state.get("plan_id") == payload.plan_id
        or provider_state.get("plan") in {plan["name"], f"{app['name']} {plan['name']}"}
    )
    if same_plan_active:
        return {
            "status": "already_active",
            "message": "This plan is already active in the connected sandbox provider account.",
            "bill": None,
            "recommendation": recommendation,
            "connection": ProviderConnectionRead.model_validate(connection).model_dump(mode="json"),
        }
    if recommendation["decision"] != "subscribe" and not payload.override_warning_acknowledged:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "recommendation_acknowledgement_required",
                "message": f"SafePay recommends: {recommendation['decision_label']}. Review the reasons before continuing.",
                "recommendation": recommendation,
            },
        )

    if not connection:
        connector = SandboxProviderConnector(definition)
        connection = ProviderConnection(
            user_id=user.id,
            provider_slug=definition.slug,
            provider_name=definition.name,
            category=definition.category,
            external_customer_id=f"MARKET-{user.id}-{definition.slug.upper()}",
            display_name=f"My {definition.name} subscription",
            connection_type=definition.connection_type,
            status="connected",
            capabilities=list(definition.capabilities),
            provider_state=connector.initial_state(),
        )
        db.add(connection)
        db.flush()

    external_obligation_id = f"MARKET-{app['slug']}-{plan['id']}-{user.id}"
    bill = db.scalar(
        select(Bill).where(
            Bill.user_id == user.id,
            Bill.external_obligation_id == external_obligation_id,
            Bill.status.in_(["due", "overdue", "scheduled"]),
        )
    )
    current_status = (connection.provider_state or {}).get("subscription_status")
    service_action = "change_subscription" if current_status == "active" else "activate_subscription"
    if not bill:
        bill = Bill(
            user_id=user.id,
            provider_connection_id=connection.id,
            external_obligation_id=external_obligation_id,
            provider_reference=connection.external_customer_id,
            name=f"{app['name']} {plan['name']}",
            biller=app["name"],
            category="subscription",
            amount=plan["price"],
            due_date=date.today(),
            recurrence=plan["billing_cycle"],
            status="due",
            external_status="awaiting_payment",
            sync_status="synced",
            service_action=service_action,
        )
        db.add(bill)
        db.flush()
    connection.provider_state = {
        **(connection.provider_state or {}),
        "pending_plan": {
            "id": plan["id"],
            "name": plan["name"],
            "price": float(plan["price"]),
            "currency": plan["currency"],
            "billing_cycle": plan["billing_cycle"],
            "external_obligation_id": external_obligation_id,
        },
        "source_of_truth": "provider",
    }
    db.add(
        MarketplaceInteraction(
            user_id=user.id,
            app_slug=app["slug"],
            plan_id=plan["id"],
            action="subscribe_intent",
            context={
                "decision": recommendation["decision"],
                "override_warning_acknowledged": payload.override_warning_acknowledged,
                "bill_id": bill.id,
            },
        )
    )
    write_audit(
        db,
        user_id=user.id,
        action="marketplace.subscription_intent_created",
        entity_type="bill",
        entity_id=bill.id,
        detail={
            "app_slug": app["slug"],
            "plan_id": plan["id"],
            "ai_decision": recommendation["decision"],
            "warning_overridden": payload.override_warning_acknowledged,
            "authorization_required": True,
        },
    )
    db.commit()
    db.refresh(bill)
    db.refresh(connection)
    return {
        "status": "payment_required",
        "message": "Subscription bill created. The provider remains inactive until you authorize payment.",
        "bill": BillRead.model_validate(bill).model_dump(mode="json"),
        "recommendation": recommendation,
        "connection": ProviderConnectionRead.model_validate(connection).model_dump(mode="json"),
        "next_step": {"page": "bills", "action": "prepare_and_authorize_payment"},
    }
