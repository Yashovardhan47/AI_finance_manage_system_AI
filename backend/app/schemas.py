from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    monthly_income: Decimal = Field(default=0, ge=0)
    minimum_balance: Decimal = Field(default=5000, ge=0)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    currency: str
    monthly_income: Decimal
    minimum_balance: Decimal
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class AccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    provider: str = Field(default="Manual", max_length=100)
    account_type: str = Field(default="bank", pattern="^(bank|wallet|card|cash)$")
    masked_identifier: str = Field(default="•••• 0000", max_length=32)
    balance: Decimal = Field(default=0, ge=0)
    reward_rate: Decimal = Field(default=0, ge=0, le=20)


class AccountRead(ORMModel):
    id: int
    name: str
    provider: str
    account_type: str
    masked_identifier: str
    balance: Decimal
    reward_rate: Decimal
    is_active: bool


class BillCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    biller: str = Field(min_length=2, max_length=120)
    category: str = Field(default="utility", pattern="^(utility|subscription|emi|insurance|recharge|rent|education|other)$")
    amount: Decimal = Field(gt=0)
    due_date: date
    recurrence: str = Field(default="monthly", pattern="^(once|weekly|monthly|quarterly|yearly)$")
    autopay_enabled: bool = False
    provider_reference: str | None = Field(default=None, max_length=180)


class BillRead(ORMModel):
    id: int
    name: str
    biller: str
    category: str
    amount: Decimal
    due_date: date
    recurrence: str
    status: str
    autopay_enabled: bool
    provider_reference: str | None


class PaymentPrepare(BaseModel):
    bill_id: int
    account_id: int
    idempotency_key: str = Field(min_length=8, max_length=120)


class PaymentRead(ORMModel):
    id: int
    bill_id: int
    account_id: int
    amount: Decimal
    provider: str
    status: str
    checkout_url: str | None
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None


class TransactionCreate(BaseModel):
    account_id: int | None = None
    kind: str = Field(default="expense", pattern="^(income|expense)$")
    category: str = Field(default="other", max_length=50)
    merchant: str = Field(default="Unknown", max_length=120)
    amount: Decimal = Field(gt=0)
    occurred_at: datetime | None = None


class TransactionRead(ORMModel):
    id: int
    account_id: int | None
    bill_id: int | None
    kind: str
    category: str
    merchant: str
    amount: Decimal
    status: str
    occurred_at: datetime


class UserPreferencesUpdate(BaseModel):
    monthly_income: Decimal | None = Field(default=None, ge=0)
    minimum_balance: Decimal | None = Field(default=None, ge=0)

