from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models import Bill, FinancialAccount, Transaction, User
from app.services.safepay import build_safe_pay_plan, detect_anomalies, financial_health, forecast_cashflow


router = APIRouter(prefix="/ai", tags=["safe-pay intelligence"])


def finance_context(db: Session, user_id: int) -> tuple[list[FinancialAccount], list[Bill], list[Transaction]]:
    accounts = list(db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user_id)))
    bills = list(db.scalars(select(Bill).where(Bill.user_id == user_id)))
    transactions = list(db.scalars(select(Transaction).where(Transaction.user_id == user_id)))
    return accounts, bills, transactions


@router.get("/health")
def health_score(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    accounts, bills, transactions = finance_context(db, user.id)
    return financial_health(user, accounts, bills, transactions)


@router.get("/forecast")
def forecast(
    days: int = Query(default=30, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    accounts, bills, transactions = finance_context(db, user.id)
    return forecast_cashflow(user, accounts, bills, transactions, days=days)


@router.get("/safe-pay-plan")
def safe_pay_plan(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    accounts, bills, transactions = finance_context(db, user.id)
    return build_safe_pay_plan(user, accounts, bills, transactions)


@router.get("/anomalies")
def anomalies(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _, _, transactions = finance_context(db, user.id)
    items = detect_anomalies(transactions)
    return {
        "items": items,
        "count": len(items),
        "disclaimer": "Flags are statistical outliers for review, not proof of fraud.",
    }

