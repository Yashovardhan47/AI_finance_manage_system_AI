from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models import ProviderConnection, ProviderEvent, User
from app.schemas import ProviderConnectionCreate, ProviderConnectionRead
from app.services.audit import write_audit
from app.services.provider_connectors import (
    SandboxProviderConnector,
    catalog_items,
    definition_for,
    sync_connection,
)


router = APIRouter(prefix="/integrations", tags=["provider integrations"])


@router.get("/catalog")
def connector_catalog() -> dict:
    return {
        "items": catalog_items(),
        "rule": "Only official/authorized APIs may update a real provider account. Unsupported providers use handoff or remain local-only.",
    }


@router.get("/connections", response_model=list[ProviderConnectionRead])
def list_connections(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ProviderConnection]:
    return list(
        db.scalars(
            select(ProviderConnection)
            .where(ProviderConnection.user_id == user.id)
            .order_by(ProviderConnection.created_at.desc())
        )
    )


@router.post("/connections", response_model=ProviderConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: ProviderConnectionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    try:
        definition = definition_for(payload.provider_slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not definition.enabled:
        raise HTTPException(
            status_code=503,
            detail=f"{definition.name} needs approved partner credentials before it can be connected",
        )
    existing = db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.user_id == user.id,
            ProviderConnection.provider_slug == payload.provider_slug,
            ProviderConnection.external_customer_id == payload.external_customer_id.strip(),
        )
    )
    if existing:
        return existing
    connector = SandboxProviderConnector(definition)
    connection = ProviderConnection(
        user_id=user.id,
        provider_slug=definition.slug,
        provider_name=definition.name,
        category=definition.category,
        external_customer_id=payload.external_customer_id.strip(),
        display_name=payload.display_name or definition.name,
        connection_type=definition.connection_type,
        status="connected",
        capabilities=list(definition.capabilities),
        provider_state=connector.initial_state(),
    )
    db.add(connection)
    db.flush()
    write_audit(
        db,
        user_id=user.id,
        action="provider.connected",
        entity_type="provider_connection",
        entity_id=connection.id,
        detail={"provider": definition.slug, "customer_reference": connection.external_customer_id},
    )
    db.commit()
    db.refresh(connection)
    return connection


@router.post("/connections/{connection_id}/sync")
def sync_provider_connection(
    connection_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    connection = db.scalar(
        select(ProviderConnection).where(ProviderConnection.id == connection_id, ProviderConnection.user_id == user.id)
    )
    if not connection:
        raise HTTPException(status_code=404, detail="Provider connection not found")
    try:
        result = sync_connection(db, connection)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    write_audit(
        db,
        user_id=user.id,
        action="provider.synced",
        entity_type="provider_connection",
        entity_id=connection.id,
        detail=result,
    )
    db.commit()
    return {"connection_id": connection.id, "provider": connection.provider_name, **result}


@router.get("/connections/{connection_id}/provider-state")
def provider_state(
    connection_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    connection = db.scalar(
        select(ProviderConnection).where(ProviderConnection.id == connection_id, ProviderConnection.user_id == user.id)
    )
    if not connection:
        raise HTTPException(status_code=404, detail="Provider connection not found")
    return {
        "connection_id": connection.id,
        "provider": connection.provider_name,
        "external_customer_id": connection.external_customer_id,
        "state": connection.provider_state,
        "source_of_truth": "provider",
        "last_synced_at": connection.last_synced_at,
    }


@router.get("/events")
def provider_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    events = list(
        db.scalars(
            select(ProviderEvent)
            .where(ProviderEvent.user_id == user.id)
            .order_by(ProviderEvent.created_at.desc())
            .limit(100)
        )
    )
    return [
        {
            "id": event.id,
            "connection_id": event.connection_id,
            "bill_id": event.bill_id,
            "payment_id": event.payment_id,
            "event_type": event.event_type,
            "status": event.status,
            "provider_reference": event.provider_reference,
            "payload": event.payload,
            "created_at": event.created_at,
        }
        for event in events
    ]

