from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models import AuditLog, Bill, FinancialAccount, Transaction, User
from app.services.audit import write_audit


router = APIRouter(tags=["system"])


@router.get("/audit-logs")
def audit_logs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    items = list(
        db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at.desc()).limit(100))
    )
    return [
        {
            "id": item.id,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "detail": item.detail,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


@router.post("/demo/seed")
def seed_demo(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(FinancialAccount.id).where(FinancialAccount.user_id == user.id).limit(1)):
        return {"seeded": False, "message": "Finance data already exists"}

    bank = FinancialAccount(
        user_id=user.id,
        name="Primary Savings",
        provider="Demo Bank",
        account_type="bank",
        masked_identifier="•••• 4821",
        balance=Decimal("68450"),
        reward_rate=Decimal("0"),
    )
    card = FinancialAccount(
        user_id=user.id,
        name="Rewards Card",
        provider="Demo Card",
        account_type="card",
        masked_identifier="•••• 7340",
        balance=Decimal("22000"),
        reward_rate=Decimal("2"),
    )
    db.add_all([bank, card])
    db.flush()
    today = date.today()
    bills = [
        Bill(user_id=user.id, name="Electricity", biller="APSPDCL", category="utility", amount=Decimal("1840"), due_date=today + timedelta(days=3)),
        Bill(user_id=user.id, name="Home Internet", biller="JioFiber", category="utility", amount=Decimal("999"), due_date=today + timedelta(days=6)),
        Bill(user_id=user.id, name="Streaming", biller="StreamFlix", category="subscription", amount=Decimal("649"), due_date=today + timedelta(days=9)),
        Bill(user_id=user.id, name="Education EMI", biller="Demo Finance", category="emi", amount=Decimal("8200"), due_date=today + timedelta(days=13)),
        Bill(user_id=user.id, name="Health Insurance", biller="SecureLife", category="insurance", amount=Decimal("4600"), due_date=today + timedelta(days=20)),
    ]
    db.add_all(bills)
    common_amounts = [420, 510, 460, 575, 490, 525, 445, 530]
    transactions = [
        Transaction(
            user_id=user.id,
            account_id=bank.id,
            kind="expense",
            category="food",
            merchant="Daily expense",
            amount=Decimal(str(amount)),
            occurred_at=datetime.now(timezone.utc) - timedelta(days=(index + 1) * 3),
        )
        for index, amount in enumerate(common_amounts)
    ]
    transactions.extend(
        [
            Transaction(user_id=user.id, account_id=bank.id, kind="expense", category="food", merchant="Unusual restaurant charge", amount=Decimal("4650"), occurred_at=datetime.now(timezone.utc) - timedelta(days=2)),
            Transaction(user_id=user.id, account_id=bank.id, kind="expense", category="transport", merchant="Metro", amount=Decimal("180"), occurred_at=datetime.now(timezone.utc) - timedelta(days=1)),
            Transaction(user_id=user.id, account_id=bank.id, kind="expense", category="shopping", merchant="Essentials", amount=Decimal("2300"), occurred_at=datetime.now(timezone.utc) - timedelta(days=7)),
        ]
    )
    db.add_all(transactions)
    user.monthly_income = user.monthly_income or Decimal("65000")
    user.minimum_balance = user.minimum_balance or Decimal("10000")
    write_audit(db, user_id=user.id, action="demo.seeded", entity_type="system", detail={"accounts": 2, "bills": len(bills)})
    db.commit()
    return {"seeded": True, "message": "Demo accounts, bills and transactions added"}

