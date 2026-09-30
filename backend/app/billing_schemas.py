from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.billing_models import BillingInterval, SubscriptionStatus


class BillingORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    price: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    billing_interval: BillingInterval
    feature_entitlements: dict = Field(default_factory=dict)
    trial_days: int = Field(default=0, ge=0, le=365)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    feature_entitlements: dict | None = None
    trial_days: int | None = Field(default=None, ge=0, le=365)


class PlanRead(BillingORMModel):
    id: int
    code: str
    name: str
    description: str
    price: Decimal
    currency: str
    billing_interval: str
    feature_entitlements: dict
    trial_days: int
    is_archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerCreate(BaseModel):
    external_key: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    country_code: str = Field(default="IN", min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=80)
    tax_id: str | None = Field(default=None, max_length=80)
    billing_address: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.upper()


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=80)
    tax_id: str | None = Field(default=None, max_length=80)
    billing_address: dict | None = None
    metadata: dict | None = None


class CustomerRead(BillingORMModel):
    id: int
    external_key: str
    name: str
    email: EmailStr
    country_code: str
    region: str | None
    tax_id: str | None
    credit_balance: Decimal
    billing_address: dict
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class SubscriptionCreate(BaseModel):
    customer_id: int
    plan_id: int
    quantity: int = Field(default=1, ge=1, le=100000)
    start_trial: bool = True
    start_at: datetime | None = None


class SubscriptionRead(BillingORMModel):
    id: int
    customer_id: int
    plan_id: int
    pending_plan_id: int | None
    status: str
    quantity: int
    trial_started_at: datetime | None
    trial_ends_at: datetime | None
    activated_at: datetime | None
    past_due_at: datetime | None
    paused_at: datetime | None
    resumes_at: datetime | None
    cancelled_at: datetime | None
    status_changed_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    next_billing_at: datetime | None
    cancel_at_period_end: bool
    cancellation_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class PlanChangeRequest(BaseModel):
    plan_id: int
    timing: Literal["immediate", "end_of_cycle"] = "immediate"


class PauseRequest(BaseModel):
    resume_at: datetime | None = None


class CancelRequest(BaseModel):
    timing: Literal["immediate", "end_of_cycle"] = "end_of_cycle"
    refund_unused: bool = False
    reason: str = Field(default="Customer requested cancellation", min_length=3, max_length=500)


class UsageCreate(BaseModel):
    subscription_id: int
    metric: str = Field(min_length=2, max_length=80)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    unit_price: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=4)
    occurred_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class TaxRateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    country_code: str = Field(min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=80)
    rate_percent: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=4)
    effective_from: date = Field(default_factory=date.today)
    effective_to: date | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.upper()


class TaxRateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    rate_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=4)
    is_active: bool | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class MockChargeRequest(BaseModel):
    invoice_id: int
    outcome: Literal["success", "failure"] | None = None
    failure_reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=160)


class GatewayWebhookPayload(BaseModel):
    event_id: str = Field(min_length=8, max_length=160)
    event_type: Literal["payment.paid", "payment.failed", "payment.refunded"]
    owner_user_id: int
    invoice_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    gateway_reference: str = Field(min_length=3, max_length=160)
    attempt_number: int = Field(default=0, ge=0, le=20)
    idempotency_key: str = Field(min_length=8, max_length=160)
    failure_code: str | None = Field(default=None, max_length=80)
    failure_reason: str | None = Field(default=None, max_length=500)


class RefundRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)


class CycleRunRequest(BaseModel):
    as_of: datetime | None = None


class RetryRunRequest(BaseModel):
    as_of: datetime | None = None
    forced_outcome: Literal["success", "failure"] | None = None


class DashboardRange(BaseModel):
    months: int = Field(default=12, ge=1, le=36)


class SubscriptionTransitionResult(BaseModel):
    subscription: SubscriptionRead
    message: str
    invoice_id: int | None = None
    refund_id: int | None = None


VALID_SUBSCRIPTION_STATUSES = {item.value for item in SubscriptionStatus}
