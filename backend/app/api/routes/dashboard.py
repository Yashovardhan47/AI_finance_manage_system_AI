from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models import Bill, FinancialAccount, Payment, ProviderConnection, Transaction, User


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    accounts = list(db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user.id, FinancialAccount.is_active.is_(True))))
    bills = list(db.scalars(select(Bill).where(Bill.user_id == user.id).order_by(Bill.due_date)))
    payments = list(db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(5)))
    connected_providers = db.scalar(
        select(func.count(ProviderConnection.id)).where(
            ProviderConnection.user_id == user.id,
            ProviderConnection.status == "connected",
        )
    ) or 0
    today = date.today()
    upcoming = [bill for bill in bills if bill.status in {"due", "scheduled", "overdue"} and bill.due_date <= today + timedelta(days=30)]
    total_balance = sum((account.balance for account in accounts), Decimal("0"))
    upcoming_total = sum((bill.amount for bill in upcoming), Decimal("0"))
    month_start = today.replace(day=1)
    spent = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user.id,
            Transaction.kind == "expense",
            func.date(Transaction.occurred_at) >= month_start,
        )
    )
    return {
        "currency": user.currency,
        "total_balance": float(total_balance),
        "upcoming_30_days": float(upcoming_total),
        "spent_this_month": float(spent or 0),
        "active_accounts": len(accounts),
        "connected_providers": connected_providers,
        "unpaid_bills": len(upcoming),
        "upcoming_bills": [
            {
                "id": bill.id,
                "name": bill.name,
                "biller": bill.biller,
                "category": bill.category,
                "amount": float(bill.amount),
                "due_date": bill.due_date.isoformat(),
                "status": bill.status,
                "external_status": bill.external_status,
                "sync_status": bill.sync_status,
            }
            for bill in upcoming[:6]
        ],
        "recent_payments": [
            {
                "id": payment.id,
                "amount": float(payment.amount),
                "status": payment.status,
                "created_at": payment.created_at.isoformat(),
            }
            for payment in payments
        ],
    }
