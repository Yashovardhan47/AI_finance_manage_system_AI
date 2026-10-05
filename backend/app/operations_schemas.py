from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ObligationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    counterparty: str = Field(min_length=2, max_length=160)
    category: str = Field(
        default="other",
        pattern="^(utility|subscription|emi|insurance|health|rent|education|tax|membership|recharge|other)$",
    )
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    due_date: date
    recurrence: str = Field(default="once", pattern="^(once|weekly|monthly|quarterly|yearly|irregular)$")
    priority: int = Field(default=3, ge=1, le=5)
    essential: bool = False
    source: str = Field(default="manual", pattern="^(manual|bill|provider|document|email)$")
    external_reference: str | None = Field(default=None, max_length=180)
    confidence: Decimal = Field(default=Decimal("0.750"), ge=0, le=1)
    contract_terms: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)


class ObligationRead(ORMModel):
    id: int
    bill_id: int | None
    provider_connection_id: int | None
    name: str
    counterparty: str
    category: str
    amount: Decimal
    currency: str
    due_date: date
    recurrence: str
    priority: int
    essential: bool
    status: str
    source: str
    external_reference: str | None
    confidence: Decimal
    contract_terms: dict
    evidence: dict
    next_action: str | None
    created_at: datetime
    updated_at: datetime


class ObligationDocumentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    media_type: str = Field(default="application/octet-stream", max_length=120)
    content_hash: str = Field(min_length=16, max_length=128)
    storage_reference: str | None = Field(default=None, max_length=500)
    extraction_status: str = Field(
        default="review_required", pattern="^(pending|extracted|review_required|verified|failed)$"
    )
    extraction_confidence: Decimal = Field(default=0, ge=0, le=1)
    extracted_fields: dict = Field(default_factory=dict)


class ObligationDocumentRead(ORMModel):
    id: int
    obligation_id: int
    filename: str
    media_type: str
    content_hash: str
    storage_reference: str | None
    extraction_status: str
    extraction_confidence: Decimal
    extracted_fields: dict
    created_at: datetime


class FinancialPolicyUpdate(BaseModel):
    autonomy_mode: str | None = Field(default=None, pattern="^(advise|prepare|execute_authorized)$")
    minimum_reserve: Decimal | None = Field(default=None, ge=0)
    max_preparable_amount: Decimal | None = Field(default=None, ge=0)
    approval_above: Decimal | None = Field(default=None, ge=0)
    allowed_categories: list[str] | None = None
    trusted_counterparties: list[str] | None = None
    require_provider_confirmation: bool | None = None
    protect_essential_first: bool | None = None
    is_active: bool | None = None


class FinancialPolicyRead(ORMModel):
    id: int
    autonomy_mode: str
    minimum_reserve: Decimal
    max_preparable_amount: Decimal
    approval_above: Decimal
    allowed_categories: list[str]
    trusted_counterparties: list[str]
    require_provider_confirmation: bool
    protect_essential_first: bool
    is_active: bool
    updated_at: datetime


class RecommendationRead(ORMModel):
    id: int
    obligation_id: int
    action: str
    status: str
    proposed_date: date | None
    proposed_amount: Decimal
    account_id: int | None
    risk_level: str
    confidence: Decimal
    rationale: dict
    forecast_snapshot: dict
    model_version: str
    created_at: datetime
    decided_at: datetime | None


class RecommendationDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    idempotency_key: str = Field(min_length=8, max_length=160)
    note: str | None = Field(default=None, max_length=500)


class ScenarioCreate(BaseModel):
    name: str = Field(default="What-if scenario", min_length=2, max_length=160)
    amount: Decimal = Field(gt=0)
    due_date: date
    category: str = Field(default="subscription", max_length=50)
    essential: bool = False
    recurring_monthly: bool = False


class OutcomeCreate(BaseModel):
    obligation_id: int
    action_request_id: int | None = None
    event_type: str = Field(
        default="provider_status_checked",
        pattern="^(payment_settled|provider_status_checked|service_activated|due_cleared|refund_received|user_reported)$",
    )
    source: str = Field(default="user", pattern="^(user|provider|gateway|reconciliation|system)$")
    status: str = Field(pattern="^(confirmed|verified|pending|mismatch|failed)$")
    provider_reference: str | None = Field(default=None, max_length=180)
    expected_status: str | None = Field(default=None, max_length=80)
    actual_status: str | None = Field(default=None, max_length=80)
    evidence: dict = Field(default_factory=dict)


class ExceptionResolve(BaseModel):
    resolution: str = Field(min_length=3, max_length=2000)


class ConsentCreate(BaseModel):
    provider_connection_id: int | None = None
    purpose: str = Field(min_length=3, max_length=240)
    data_categories: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
