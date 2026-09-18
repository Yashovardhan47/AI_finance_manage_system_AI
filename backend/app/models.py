from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    minimum_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=5000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    accounts: Mapped[list[FinancialAccount]] = relationship(back_populates="user", cascade="all, delete-orphan")
    bills: Mapped[list[Bill]] = relationship(back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="user", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(back_populates="user", cascade="all, delete-orphan")
    provider_connections: Mapped[list[ProviderConnection]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    marketplace_interactions: Mapped[list[MarketplaceInteraction]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100), default="Manual")
    account_type: Mapped[str] = mapped_column(String(40), default="bank")
    masked_identifier: Mapped[str] = mapped_column(String(32), default="•••• 0000")
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    reward_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="accounts")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="account")
    payments: Mapped[list[Payment]] = relationship(back_populates="account")


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider_slug", "external_customer_id", name="uq_provider_customer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider_slug: Mapped[str] = mapped_column(String(80), index=True)
    provider_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40), index=True)
    external_customer_id: Mapped[str] = mapped_column(String(180))
    display_name: Mapped[str] = mapped_column(String(120))
    connection_type: Mapped[str] = mapped_column(String(30), default="sandbox")
    status: Mapped[str] = mapped_column(String(30), default="connected")
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    credential_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_state: Mapped[dict] = mapped_column(JSON, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="provider_connections")
    bills: Mapped[list[Bill]] = relationship(back_populates="provider_connection")
    events: Mapped[list[ProviderEvent]] = relationship(back_populates="connection", cascade="all, delete-orphan")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    biller: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40), default="utility")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    recurrence: Mapped[str] = mapped_column(String(30), default="monthly")
    status: Mapped[str] = mapped_column(String(30), default="due", index=True)
    autopay_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    external_obligation_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    external_status: Mapped[str] = mapped_column(String(40), default="not_linked")
    sync_status: Mapped[str] = mapped_column(String(40), default="local_only")
    service_action: Mapped[str] = mapped_column(String(50), default="clear_due")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="bills")
    provider_connection: Mapped[ProviderConnection | None] = relationship(back_populates="bills")
    payments: Mapped[list[Payment]] = relationship(back_populates="bill")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="bill")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("financial_accounts.id"), nullable=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="expense")
    category: Mapped[str] = mapped_column(String(50), default="other", index=True)
    merchant: Mapped[str] = mapped_column(String(120), default="Unknown")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(30), default="posted")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="transactions")
    account: Mapped[FinancialAccount | None] = relationship(back_populates="transactions")
    bill: Mapped[Bill | None] = relationship(back_populates="transactions")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_payment_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    provider: Mapped[str] = mapped_column(String(50), default="sandbox")
    status: Mapped[str] = mapped_column(String(30), default="requires_authorization")
    idempotency_key: Mapped[str] = mapped_column(String(120))
    checkout_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_sync_status: Mapped[str] = mapped_column(String(40), default="not_required")
    provider_confirmation_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="payments")
    bill: Mapped[Bill] = relationship(back_populates="payments")
    account: Mapped[FinancialAccount] = relationship(back_populates="payments")


class ProviderEvent(Base):
    __tablename__ = "provider_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("provider_connections.id", ondelete="CASCADE"), index=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id", ondelete="SET NULL"), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="received")
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    connection: Mapped[ProviderConnection] = relationship(back_populates="events")


class MarketplaceInteraction(Base):
    __tablename__ = "marketplace_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    app_slug: Mapped[str] = mapped_column(String(80), index=True)
    plan_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="marketplace_interactions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
