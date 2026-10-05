from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Obligation(Base):
    __tablename__ = "financial_obligations"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "external_reference", name="uq_obligation_source_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    counterparty: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    due_date: Mapped[date] = mapped_column(Date, index=True)
    recurrence: Mapped[str] = mapped_column(String(30), default="once")
    priority: Mapped[int] = mapped_column(default=3)
    essential: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(35), default="detected", index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    external_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.750"))
    contract_terms: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    next_action: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ObligationDocument(Base):
    __tablename__ = "obligation_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("financial_obligations.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(240))
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    storage_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(30), default="review_required")
    extraction_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.000"))
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinancialPolicy(Base):
    __tablename__ = "financial_policies"
    __table_args__ = (UniqueConstraint("user_id", name="uq_financial_policy_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    autonomy_mode: Mapped[str] = mapped_column(String(30), default="advise")
    minimum_reserve: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5000"))
    max_preparable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5000"))
    approval_above: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    allowed_categories: Mapped[list] = mapped_column(JSON, default=list)
    trusted_counterparties: Mapped[list] = mapped_column(JSON, default=list)
    require_provider_confirmation: Mapped[bool] = mapped_column(Boolean, default=True)
    protect_essential_first: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purpose: Mapped[str] = mapped_column(String(240))
    data_categories: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    consent_reference: Mapped[str] = mapped_column(String(180), unique=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Recommendation(Base):
    __tablename__ = "financial_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("financial_obligations.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(35), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    proposed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True
    )
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    rationale: Mapped[dict] = mapped_column(JSON, default=dict)
    forecast_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(80), default="financial-ops-rules-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionRequest(Base):
    __tablename__ = "financial_action_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_action_request_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("financial_recommendations.id", ondelete="CASCADE"), index=True
    )
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("financial_obligations.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="pending_approval", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scenario(Base):
    __tablename__ = "financial_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    assumptions: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutcomeEvent(Base):
    __tablename__ = "financial_outcome_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("financial_obligations.id", ondelete="CASCADE"), index=True
    )
    action_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_action_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    source: Mapped[str] = mapped_column(String(40), default="user")
    status: Mapped[str] = mapped_column(String(30), index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ExceptionCase(Base):
    __tablename__ = "financial_exception_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("financial_obligations.id", ondelete="CASCADE"), index=True
    )
    outcome_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_outcome_events.id", ondelete="SET NULL"), nullable=True
    )
    case_type: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(25), default="open", index=True)
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
