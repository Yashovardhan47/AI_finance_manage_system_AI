"""Provider-account connectors and synchronization orchestration.

The sandbox connectors exercise the same lifecycle used by official APIs:
connect account -> fetch obligation -> pay with customer reference -> verify
provider settlement -> update the provider-facing account state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, MarketplaceInteraction, Payment, ProviderConnection, ProviderEvent


@dataclass(frozen=True)
class ConnectorDefinition:
    slug: str
    name: str
    category: str
    description: str
    connection_type: str
    capabilities: tuple[str, ...]
    enabled: bool
    production_ready: bool
    onboarding: str

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "connection_type": self.connection_type,
            "capabilities": list(self.capabilities),
            "enabled": self.enabled,
            "production_ready": self.production_ready,
            "onboarding": self.onboarding,
        }


CATALOG: dict[str, ConnectorDefinition] = {
    "gridhome_energy": ConnectorDefinition(
        slug="gridhome_energy",
        name="GridHome Energy",
        category="home",
        description="Sandbox electricity provider with bill inquiry, posting and due-clearance confirmation.",
        connection_type="sandbox",
        capabilities=("bill_inquiry", "payment_posting", "due_clearance", "status_sync"),
        enabled=True,
        production_ready=False,
        onboarding="Enter the demo consumer number; no password is collected.",
    ),
    "medicare_health": ConnectorDefinition(
        slug="medicare_health",
        name="MediCare Health",
        category="health",
        description="Sandbox health/insurance provider with invoice synchronization and coverage confirmation.",
        connection_type="sandbox",
        capabilities=("invoice_inquiry", "payment_posting", "due_clearance", "coverage_sync"),
        enabled=True,
        production_ready=False,
        onboarding="Enter the demo member ID; no medical records or password are collected.",
    ),
    "streamplus": ConnectorDefinition(
        slug="streamplus",
        name="StreamPlus",
        category="entertainment",
        description="Sandbox streaming provider supporting plan purchase, renewal and subscription-state sync.",
        connection_type="sandbox",
        capabilities=("plan_inquiry", "subscription_purchase", "renewal", "subscription_sync"),
        enabled=True,
        production_ready=False,
        onboarding="Enter the demo entertainment account ID.",
    ),
    "musicwave": ConnectorDefinition(
        slug="musicwave",
        name="MusicWave",
        category="entertainment",
        description="Sandbox music membership provider with plan purchase and subscription-state sync.",
        connection_type="sandbox",
        capabilities=("plan_inquiry", "subscription_purchase", "renewal", "subscription_sync"),
        enabled=True,
        production_ready=False,
        onboarding="Enter the demo music account ID.",
    ),
    "cloudbox": ConnectorDefinition(
        slug="cloudbox",
        name="CloudBox",
        category="productivity",
        description="Sandbox cloud-storage provider with plan purchase, renewal and entitlement sync.",
        connection_type="sandbox",
        capabilities=("plan_inquiry", "subscription_purchase", "renewal", "subscription_sync"),
        enabled=True,
        production_ready=False,
        onboarding="Enter the demo cloud account ID.",
    ),
    "fitpulse": ConnectorDefinition(
        slug="fitpulse",
        name="FitPulse",
        category="wellness",
        description="Sandbox wellness membership provider with plan purchase and membership-state sync.",
        connection_type="sandbox",
        capabilities=("plan_inquiry", "subscription_purchase", "renewal", "subscription_sync"),
        enabled=True,
        production_ready=False,
        onboarding="Enter the demo wellness account ID.",
    ),
    "learnpro": ConnectorDefinition(
        slug="learnpro",
        name="LearnPro",
        category="education",
        description="Sandbox learning provider with plan purchase, renewal and access-state sync.",
        connection_type="sandbox",
        capabilities=("plan_inquiry", "subscription_purchase", "renewal", "subscription_sync"),
        enabled=True,
        production_ready=False,
        onboarding="Enter the demo learning account ID.",
    ),
    "bharat_connect": ConnectorDefinition(
        slug="bharat_connect",
        name="Bharat Connect / BBPS partner",
        category="multi-category",
        description="Production route for supported Indian billers through an authorized Bharat Connect partner.",
        connection_type="official_api",
        capabilities=("biller_discovery", "bill_inquiry", "payment_posting", "status_inquiry", "reconciliation"),
        enabled=False,
        production_ready=True,
        onboarding="Requires an approved partner contract, credentials, certificates and webhook configuration.",
    ),
}


class SandboxProviderConnector:
    def __init__(self, definition: ConnectorDefinition):
        self.definition = definition

    def initial_state(self) -> dict:
        if "subscription_purchase" in self.definition.capabilities:
            return {"subscription_status": "inactive", "plan": None, "source_of_truth": "provider"}
        if self.definition.slug == "medicare_health":
            return {"due_status": "outstanding", "coverage_status": "pending", "source_of_truth": "provider"}
        return {"due_status": "outstanding", "service_status": "active", "source_of_truth": "provider"}

    def fetch_obligations(self, connection: ProviderConnection) -> list[dict]:
        today = date.today()
        state = connection.provider_state or self.initial_state()
        suffix = connection.external_customer_id[-6:].upper()
        if self.definition.slug == "gridhome_energy":
            cleared = state.get("due_status") == "cleared"
            return [{
                "external_id": f"GH-{suffix}-{today:%Y%m}",
                "name": "Home electricity",
                "biller": self.definition.name,
                "category": "utility",
                "amount": Decimal("2130.00"),
                "due_date": today + timedelta(days=5),
                "recurrence": "monthly",
                "external_status": "cleared" if cleared else "due",
                "service_action": "clear_due",
            }]
        if self.definition.slug == "medicare_health":
            cleared = state.get("due_status") == "cleared"
            return [{
                "external_id": f"MH-{suffix}-{today:%Y%m}",
                "name": "Family health premium",
                "biller": self.definition.name,
                "category": "insurance",
                "amount": Decimal("6750.00"),
                "due_date": today + timedelta(days=9),
                "recurrence": "monthly",
                "external_status": "cleared" if cleared else "due",
                "service_action": "clear_due",
            }]
        if self.definition.slug == "streamplus":
            active = state.get("subscription_status") == "active"
            return [{
                "external_id": f"SP-{suffix}-PREMIUM",
                "name": "StreamPlus Premium",
                "biller": self.definition.name,
                "category": "subscription",
                "amount": Decimal("799.00"),
                "due_date": today + timedelta(days=2),
                "recurrence": "monthly",
                "external_status": "active" if active else "awaiting_payment",
                "service_action": "renew_subscription" if active else "activate_subscription",
            }]
        pending_plan = state.get("pending_plan")
        if pending_plan:
            return [{
                "external_id": pending_plan["external_obligation_id"],
                "name": f"{self.definition.name} {pending_plan['name']}",
                "biller": self.definition.name,
                "category": "subscription",
                "amount": Decimal(str(pending_plan["price"])),
                "due_date": today,
                "recurrence": pending_plan["billing_cycle"],
                "external_status": "awaiting_payment",
                "service_action": "activate_subscription",
            }]
        return []

    def apply_payment(self, connection: ProviderConnection, bill: Bill, payment: Payment) -> dict:
        confirmation = f"{self.definition.slug.upper()}-{payment.id:08d}"
        common = {
            "last_confirmation_id": confirmation,
            "last_payment_amount": float(payment.amount),
            "last_payment_at": datetime.now(timezone.utc).isoformat(),
            "source_of_truth": "provider",
        }
        if bill.service_action in {"activate_subscription", "renew_subscription", "change_subscription"}:
            pending_plan = (connection.provider_state or {}).get("pending_plan") or {}
            validity_days = {"weekly": 7, "monthly": 30, "quarterly": 90, "yearly": 365}.get(
                bill.recurrence, 30
            )
            state = {
                **(connection.provider_state or {}),
                **common,
                "subscription_status": "active",
                "plan": pending_plan.get("name", bill.name),
                "plan_id": pending_plan.get("id"),
                "billing_cycle": pending_plan.get("billing_cycle", bill.recurrence),
                "valid_until": (date.today() + timedelta(days=validity_days)).isoformat(),
            }
            state.pop("pending_plan", None)
            external_status = "active"
            if bill.service_action == "activate_subscription":
                result_action = "subscription_activated"
            elif bill.service_action == "change_subscription":
                result_action = "subscription_changed"
            else:
                result_action = "subscription_renewed"
        elif self.definition.slug == "medicare_health":
            state = {**(connection.provider_state or {}), **common, "due_status": "cleared", "coverage_status": "active"}
            external_status = "cleared"
            result_action = "health_due_cleared"
        else:
            state = {**(connection.provider_state or {}), **common, "due_status": "cleared", "service_status": "active"}
            external_status = "cleared"
            result_action = "utility_due_cleared"
        return {
            "confirmation_id": confirmation,
            "external_status": external_status,
            "result_action": result_action,
            "provider_state": state,
        }


def catalog_items() -> list[dict]:
    return [definition.as_dict() for definition in CATALOG.values()]


def definition_for(slug: str) -> ConnectorDefinition:
    definition = CATALOG.get(slug)
    if not definition:
        raise ValueError("Unknown provider connector")
    return definition


def connector_for(connection: ProviderConnection) -> SandboxProviderConnector:
    definition = definition_for(connection.provider_slug)
    if not definition.enabled or definition.connection_type != "sandbox":
        raise ValueError("This official connector requires provider onboarding and credentials")
    return SandboxProviderConnector(definition)


def sync_connection(db: Session, connection: ProviderConnection) -> dict:
    connector = connector_for(connection)
    obligations = connector.fetch_obligations(connection)
    imported = 0
    updated = 0
    for item in obligations:
        bill = db.scalar(
            select(Bill).where(
                Bill.user_id == connection.user_id,
                Bill.provider_connection_id == connection.id,
                Bill.external_obligation_id == item["external_id"],
            )
        )
        mapped_status = "paid" if item["external_status"] in {"cleared", "active"} else "due"
        if not bill:
            bill = Bill(
                user_id=connection.user_id,
                provider_connection_id=connection.id,
                external_obligation_id=item["external_id"],
                provider_reference=connection.external_customer_id,
                name=item["name"],
                biller=item["biller"],
                category=item["category"],
                amount=item["amount"],
                due_date=item["due_date"],
                recurrence=item["recurrence"],
                external_status=item["external_status"],
                sync_status="synced",
                service_action=item["service_action"],
                status=mapped_status,
            )
            db.add(bill)
            imported += 1
        else:
            bill.amount = item["amount"]
            bill.due_date = item["due_date"]
            bill.external_status = item["external_status"]
            bill.sync_status = "synced"
            bill.service_action = item["service_action"]
            bill.status = mapped_status
            updated += 1
    now = datetime.now(timezone.utc)
    connection.last_synced_at = now
    event = ProviderEvent(
        user_id=connection.user_id,
        connection_id=connection.id,
        event_type="provider.sync_completed",
        status="confirmed",
        payload={"imported": imported, "updated": updated, "obligations": len(obligations)},
    )
    db.add(event)
    return {"imported": imported, "updated": updated, "obligations": len(obligations), "synced_at": now.isoformat()}


def settle_external_provider(db: Session, payment: Payment) -> dict | None:
    bill = payment.bill
    connection = bill.provider_connection
    if not connection:
        payment.provider_sync_status = "not_required"
        return None
    connector = connector_for(connection)
    payment.provider_sync_status = "posting"
    result = connector.apply_payment(connection, bill, payment)
    connection.provider_state = result["provider_state"]
    connection.last_synced_at = datetime.now(timezone.utc)
    bill.external_status = result["external_status"]
    bill.sync_status = "synced"
    payment.provider_sync_status = "confirmed"
    payment.provider_confirmation_id = result["confirmation_id"]
    db.add(
        ProviderEvent(
            user_id=payment.user_id,
            connection_id=connection.id,
            bill_id=bill.id,
            payment_id=payment.id,
            event_type=f"provider.{result['result_action']}",
            status="confirmed",
            provider_reference=result["confirmation_id"],
            payload={
                "external_customer_id": connection.external_customer_id,
                "external_obligation_id": bill.external_obligation_id,
                "external_status": result["external_status"],
                "amount": float(payment.amount),
            },
        )
    )
    if result["result_action"] in {"subscription_activated", "subscription_changed"}:
        db.add(
            MarketplaceInteraction(
                user_id=payment.user_id,
                app_slug=connection.provider_slug,
                plan_id=result["provider_state"].get("plan_id"),
                action="subscribed",
                context={"bill_id": bill.id, "payment_id": payment.id, "confirmation_id": result["confirmation_id"]},
            )
        )
    return result
