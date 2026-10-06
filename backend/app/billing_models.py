from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SubscriptionStatus(str, PyEnum):
    trial = "trial"
    active = "active"
    past_due = "past_due"
    paused = "paused"
    cancelled = "cancelled"


class BillingInterval(str, PyEnum):
    monthly = "monthly"
    annual = "annual"


class BillingCycleStatus(str, PyEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class InvoiceStatus(str, PyEnum):
    draft = "draft"
    open = "open"
    paid = "paid"
    failed = "failed"
    partially_refunded = "partially_refunded"
    refunded = "refunded"
    void = "void"


class InvoiceLineType(str, PyEnum):
    plan_fee = "plan_fee"
    proration_credit = "proration_credit"
    proration_debit = "proration_debit"
    usage = "usage"
    tax = "tax"
    refund = "refund"


class BillingPaymentStatus(str, PyEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class RetryStatus(str, PyEnum):
    queued = "queued"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class RefundStatus(str, PyEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


class NotificationStatus(str, PyEnum):
    queued = "queued"
    sent = "sent"
    failed = "failed"


class BillingPlan(Base):
    __tablename__ = "billing_plans"
    __table_args__ = (UniqueConstraint("owner_user_id", "code", name="uq_billing_plan_owner_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    billing_interval: Mapped[BillingInterval] = mapped_column(
        Enum(BillingInterval, name="billing_interval_enum", validate_strings=True)
    )
    feature_entitlements: Mapped[dict] = mapped_column(JSON, default=dict)
    trial_days: Mapped[int] = mapped_column(default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    subscriptions: Mapped[list[BillingSubscription]] = relationship(
        foreign_keys="BillingSubscription.plan_id", back_populates="plan"
    )


class BillingCustomer(Base):
    __tablename__ = "billing_customers"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "external_key", name="uq_billing_customer_owner_external_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    external_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), index=True)
    country_code: Mapped[str] = mapped_column(String(2), default="IN", index=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    credit_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    billing_address: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    subscriptions: Mapped[list[BillingSubscription]] = relationship(back_populates="customer")
    invoices: Mapped[list[BillingInvoice]] = relationship(back_populates="customer")


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("billing_customers.id", ondelete="RESTRICT"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("billing_plans.id", ondelete="RESTRICT"), index=True)
    pending_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status_enum", validate_strings=True),
        default=SubscriptionStatus.trial,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(default=1)
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    past_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resumes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_billing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    customer: Mapped[BillingCustomer] = relationship(back_populates="subscriptions")
    plan: Mapped[BillingPlan] = relationship(foreign_keys=[plan_id], back_populates="subscriptions")
    pending_plan: Mapped[BillingPlan | None] = relationship(foreign_keys=[pending_plan_id])
    cycles: Mapped[list[BillingCycle]] = relationship(back_populates="subscription")
    usage_records: Mapped[list[UsageRecord]] = relationship(back_populates="subscription")
    invoices: Mapped[list[BillingInvoice]] = relationship(back_populates="subscription")


class BillingCycle(Base):
    __tablename__ = "billing_cycles"
    __table_args__ = (
        UniqueConstraint("subscription_id", "period_start", name="uq_billing_cycle_subscription_period"),
        UniqueConstraint("idempotency_key", name="uq_billing_cycle_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("billing_invoices.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[BillingCycleStatus] = mapped_column(
        Enum(BillingCycleStatus, name="billing_cycle_status_enum", validate_strings=True),
        default=BillingCycleStatus.pending,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    attempt_count: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscription: Mapped[BillingSubscription] = relationship(back_populates="cycles")


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("owner_user_id", "idempotency_key", name="uq_usage_owner_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="CASCADE"), index=True
    )
    billed_invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    metric: Mapped[str] = mapped_column(String(80), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscription: Mapped[BillingSubscription] = relationship(back_populates="usage_records")


class InvoiceCounter(Base):
    __tablename__ = "invoice_counters"
    __table_args__ = (UniqueConstraint("owner_user_id", "period_key", name="uq_invoice_counter_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    period_key: Mapped[str] = mapped_column(String(6))
    current_value: Mapped[int] = mapped_column(default=0)


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "invoice_number", name="uq_invoice_owner_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("billing_customers.id", ondelete="RESTRICT"), index=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="RESTRICT"), index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum", validate_strings=True),
        default=InvoiceStatus.open,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    proration_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    usage_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount_refunded: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_terms: Mapped[str] = mapped_column(String(180), default="Due on receipt")
    pdf_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    customer: Mapped[BillingCustomer] = relationship(back_populates="invoices")
    subscription: Mapped[BillingSubscription] = relationship(back_populates="invoices")
    line_items: Mapped[list[InvoiceLineItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLineItem.id"
    )
    payments: Mapped[list[BillingPayment]] = relationship(back_populates="invoice")
    refunds: Mapped[list[BillingRefund]] = relationship(back_populates="invoice")
    retries: Mapped[list[PaymentRetry]] = relationship(back_populates="invoice")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("billing_invoices.id", ondelete="CASCADE"), index=True)
    line_type: Mapped[InvoiceLineType] = mapped_column(
        Enum(InvoiceLineType, name="invoice_line_type_enum", validate_strings=True), index=True
    )
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=1)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped[BillingInvoice] = relationship(back_populates="line_items")


class BillingPayment(Base):
    __tablename__ = "billing_payments"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_billing_payment_owner_idempotency"),
        UniqueConstraint("gateway_event_id", name="uq_billing_payment_gateway_event"),
        Index("ix_billing_payment_poll_claim", "status", "next_status_check_at", "processing_state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("billing_invoices.id", ondelete="RESTRICT"), index=True)
    status: Mapped[BillingPaymentStatus] = mapped_column(
        Enum(BillingPaymentStatus, name="billing_payment_status_enum", validate_strings=True),
        default=BillingPaymentStatus.pending,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    gateway: Mapped[str] = mapped_column(String(60), default="mock_gateway")
    gateway_event_id: Mapped[str] = mapped_column(String(160))
    gateway_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    attempt_number: Mapped[int] = mapped_column(default=0)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_state: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    provider_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_status_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_status_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    timed_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped[BillingInvoice] = relationship(back_populates="payments")


class PaymentRetry(Base):
    __tablename__ = "payment_retries"
    __table_args__ = (UniqueConstraint("invoice_id", "attempt_number", name="uq_retry_invoice_attempt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("billing_invoices.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="CASCADE"), index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_payments.id", ondelete="SET NULL"), nullable=True
    )
    attempt_number: Mapped[int] = mapped_column()
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[RetryStatus] = mapped_column(
        Enum(RetryStatus, name="retry_status_enum", validate_strings=True),
        default=RetryStatus.queued,
        index=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped[BillingInvoice] = relationship(back_populates="retries")


class BillingRefund(Base):
    __tablename__ = "billing_refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("billing_invoices.id", ondelete="RESTRICT"), index=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_payments.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[RefundStatus] = mapped_column(
        Enum(RefundStatus, name="refund_status_enum", validate_strings=True),
        default=RefundStatus.pending,
        index=True,
    )
    gateway_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    invoice: Mapped[BillingInvoice] = relationship(back_populates="refunds")


class TaxRate(Base):
    __tablename__ = "tax_rates"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "country_code", "region", "name", name="uq_tax_rate_scope_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BillingNotification(Base):
    __tablename__ = "billing_notifications"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "dedupe_key", name="uq_billing_notification_owner_dedupe"),
        Index(
            "ix_billing_notification_claim",
            "delivery_status",
            "next_attempt_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("billing_customers.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    recipient: Mapped[str] = mapped_column(String(320))
    channel: Mapped[str] = mapped_column(String(30), default="email")
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status_enum", validate_strings=True),
        default=NotificationStatus.queued,
        index=True,
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    delivery_status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="sandbox")
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    provider_response: Mapped[dict] = mapped_column(JSON, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    escalation_level: Mapped[int] = mapped_column(default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "customer_id", name="uq_notification_preference_owner_customer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("billing_customers.id", ondelete="CASCADE"), index=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    email_address: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    push_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_types: Mapped[list] = mapped_column(JSON, default=lambda: ["*"])
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    timezone_name: Mapped[str] = mapped_column(String(80), default="UTC")
    escalation_rules: Mapped[list] = mapped_column(
        JSON,
        default=lambda: [
            {"after_minutes": 5, "channels": ["email"]},
            {"after_minutes": 15, "channels": ["sms", "push"]},
        ],
    )
    max_delivery_attempts: Mapped[int] = mapped_column(default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PaymentIncident(Base):
    __tablename__ = "payment_incidents"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "dedupe_key", name="uq_payment_incident_owner_dedupe"),
        Index("ix_payment_incident_escalation_claim", "status", "next_escalation_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    incident_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(25), default="open", index=True)
    summary: Mapped[str] = mapped_column(String(300))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(180))
    escalation_level: Mapped[int] = mapped_column(default=0)
    next_escalation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class NotificationReceipt(Base):
    __tablename__ = "notification_receipts"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_notification_receipt_provider_event"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("billing_notifications.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    event_id: Mapped[str] = mapped_column(String(180))
    provider_message_id: Mapped[str] = mapped_column(String(180), index=True)
    delivery_status: Mapped[str] = mapped_column(String(30), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentReconciliation(Base):
    __tablename__ = "payment_reconciliations"
    __table_args__ = (
        UniqueConstraint("payment_id", "provider_check_id", name="uq_payment_reconciliation_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("billing_payments.id", ondelete="CASCADE"), index=True)
    provider_check_id: Mapped[str] = mapped_column(String(180))
    previous_status: Mapped[str] = mapped_column(String(40))
    provider_status: Mapped[str] = mapped_column(String(80), index=True)
    resolved_status: Mapped[str] = mapped_column(String(40), index=True)
    provider_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RealtimeBillingEvent(Base):
    __tablename__ = "realtime_billing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class TaskDeadLetter(Base):
    __tablename__ = "task_dead_letters"
    __table_args__ = (UniqueConstraint("task_id", name="uq_task_dead_letter_task_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(180))
    task_name: Mapped[str] = mapped_column(String(180), index=True)
    queue_name: Mapped[str] = mapped_column(String(80), default="billing.dead_letter")
    args: Mapped[list] = mapped_column(JSON, default=list)
    kwargs: Mapped[dict] = mapped_column(JSON, default=dict)
    exception_type: Mapped[str] = mapped_column(String(160))
    exception_message: Mapped[str] = mapped_column(Text)
    traceback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(25), default="unresolved", index=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"
    __table_args__ = (UniqueConstraint("gateway", "event_id", name="uq_billing_webhook_gateway_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    gateway: Mapped[str] = mapped_column(String(60), default="mock_gateway")
    event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
